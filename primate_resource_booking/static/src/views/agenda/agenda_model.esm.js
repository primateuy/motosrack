/** @odoo-module **/

/**
 * Data behind the agenda.
 *
 * Three reads, every one of them scoped to the window on screen:
 *   - the records of the view's model that touch the window,
 *   - every row of the grouping model, booked or not, so an empty agenda
 *     still shows the fleet,
 *   - the records of the overlay model, if the arch declares one.
 */

import {Domain} from "@web/core/domain";
import {Model} from "@web/model/model";
import {KeepLast} from "@web/core/utils/concurrency";
import {deserializeDateTime, serializeDateTime} from "@web/core/l10n/dates";
import {evaluateExpr} from "@web/core/py_js/py";
import {onWillStart} from "@odoo/owl";

export class AgendaModel extends Model {
    setup(params) {
        this.params = params;
        this.resModel = params.resModel;
        this.fields = params.fields;
        this.keepLast = new KeepLast();

        this.records = [];
        this.rows = [];
        this.overlays = [];
        this.searchParams = {domain: [], context: {}};
        this.window = null;

        this.canCreate = true;
        this.canWrite = true;

        onWillStart(async () => {
            // has_access is a method on records, so the ids come first even
            // though the check is on the model.
            const [create, write] = await Promise.all([
                this.orm.call(this.resModel, "has_access", [[], "create"]),
                this.orm.call(this.resModel, "has_access", [[], "write"]),
            ]);
            this.canCreate = create;
            this.canWrite = write;
        });
    }

    /**
     * Called by the view on every search change, and by the controller when
     * the window moves. Without a window yet there is nothing to read: the
     * renderer sets one as soon as it knows the scale.
     */
    async load(searchParams) {
        if (searchParams) {
            this.searchParams = searchParams;
        }
        if (!this.window) {
            return;
        }
        await this.keepLast.add(this.fetch());
        this.notify();
    }

    async setWindow(start, stop) {
        this.window = {start, stop};
        await this.load();
    }

    windowDomain(dateStart, dateStop) {
        // Half-open overlap: it ends after the window starts and starts
        // before the window ends.
        return [
            [dateStop, ">", serializeDateTime(this.window.start)],
            [dateStart, "<", serializeDateTime(this.window.stop)],
        ];
    }

    async fetch() {
        const {dateStart, dateStop, fieldNames, groupBy, rowModel} = this.params;
        const context = this.searchParams.context || {};

        const reads = [
            this.orm.webSearchRead(this.resModel, [
                ...(this.searchParams.domain || []),
                ...this.windowDomain(dateStart, dateStop),
            ], {
                specification: Object.fromEntries(
                    fieldNames.map((name) => [name, this.fieldSpec(this.fields[name])])
                ),
                context: context,
            }),
            this.orm.webSearchRead(rowModel, evaluateExpr(this.params.rowDomain), {
                specification: {display_name: {}},
                limit: this.params.rowLimit,
                order: this.params.rowOrder || "",
                context: context,
            }),
        ];

        if (this.params.overlay) {
            const overlay = this.params.overlay;
            // An open block has no end, so it cannot be filtered out by one:
            // those are kept whenever they started before the window ends.
            const touchesWindow = Domain.or([
                Domain.and([
                    new Domain([[overlay.dateStop, "!=", false]]),
                    new Domain(this.windowDomain(overlay.dateStart, overlay.dateStop)),
                ]),
                new Domain([
                    [overlay.dateStop, "=", false],
                    [overlay.dateStart, "<", serializeDateTime(this.window.stop)],
                ]),
            ]);
            reads.push(
                this.orm.webSearchRead(overlay.resModel, Domain.and([
                    new Domain(evaluateExpr(overlay.domain)),
                    touchesWindow,
                ]).toList(), {
                    specification: {
                        display_name: {},
                        [overlay.dateStart]: {},
                        [overlay.dateStop]: {},
                        [overlay.groupBy]: {fields: {display_name: {}}},
                        [overlay.label]: overlay.label === "display_name"
                            ? {}
                            : {fields: {display_name: {}}},
                    },
                    context: context,
                })
            );
        }

        const [records, rows, overlays] = await Promise.all(reads);

        this.records = records.records.map((record) => this.toEvent(record));
        this.rows = rows.records.map((row) => ({id: row.id, name: row.display_name}));
        this.overlays = overlays
            ? overlays.records.map((record) => this.toOverlay(record))
            : [];
    }

    fieldSpec(field) {
        return field && field.type === "many2one" ? {fields: {display_name: {}}} : {};
    }

    toEvent(record) {
        const {dateStart, dateStop, groupBy, label, state, chain} = this.params;
        return {
            id: record.id,
            resId: record.id,
            rowId: record[groupBy] ? record[groupBy].id : false,
            start: deserializeDateTime(record[dateStart]),
            stop: deserializeDateTime(record[dateStop]),
            label: this.textOf(record, label),
            state: state ? record[state] : false,
            chained: Boolean(chain && record[chain]),
            overlay: false,
        };
    }

    toOverlay(record) {
        const overlay = this.params.overlay;
        const stop = record[overlay.dateStop];
        return {
            id: record.id,
            resId: record.id,
            resModel: overlay.resModel,
            rowId: record[overlay.groupBy] ? record[overlay.groupBy].id : false,
            start: deserializeDateTime(record[overlay.dateStart]),
            // An open block runs to the end of the window and says so.
            stop: stop ? deserializeDateTime(stop) : this.window.stop,
            open: !stop,
            label: this.textOf(record, overlay.label),
            overlay: true,
        };
    }

    textOf(record, fieldName) {
        const value = record[fieldName];
        if (value && typeof value === "object") {
            return value.display_name || "";
        }
        return value ? String(value) : "";
    }

    /**
     * Move or stretch a record. Returns false when the write is refused, so
     * the renderer can put the bar back where it was.
     */
    async writeDates(resId, start, stop) {
        const {dateStart, dateStop} = this.params;
        await this.orm.write(this.resModel, [resId], {
            [dateStart]: serializeDateTime(start),
            [dateStop]: serializeDateTime(stop),
        });
        await this.load();
    }
}
