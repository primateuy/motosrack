/** @odoo-module **/

/**
 * Draws the agenda: one row per resource, one column per day, and a bar for
 * every record that takes a row between two dates.
 *
 * Everything is laid out from the window the controller hands over, so the
 * same renderer serves a week, a fortnight or a month without knowing what
 * is being booked.
 */

import {Component, useRef, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";

const {DateTime} = luxon;

// Grab zone, in pixels, at each end of a bar.
const HANDLE = 9;

export class AgendaRenderer extends Component {
    static template = "primate_resource_booking.AgendaRenderer";
    static props = {
        model: Object,
        scale: String,
        density: String,
        variant: String,
        windowStart: Object,
        columnCount: Number,
        onCreateRange: Function,
        onOpenRecord: Function,
        onMoveRecord: Function,
    };

    setup() {
        this.rootRef = useRef("root");
        this.state = useState({drag: null});
    }

    // ------------------------------------------------------------------
    // Layout
    // ------------------------------------------------------------------

    get columns() {
        const start = this.props.windowStart;
        const today = DateTime.local().startOf("day");
        return Array.from({length: this.props.columnCount}, (_, index) => {
            const date = start.plus({days: index});
            return {
                index: index,
                date: date,
                day: date.day,
                dow: date.toFormat("ccc"),
                weekend: date.weekday >= 6,
                today: date.hasSame(today, "day"),
            };
        });
    }

    get months() {
        const groups = [];
        for (const column of this.columns) {
            const key = column.date.toFormat("yyyy-MM");
            const last = groups[groups.length - 1];
            if (last && last.key === key) {
                last.span += 1;
            } else {
                groups.push({
                    key: key,
                    span: 1,
                    label: column.date.toFormat("LLLL yyyy"),
                });
            }
        }
        return groups;
    }

    get windowStop() {
        return this.props.windowStart.plus({days: this.props.columnCount});
    }

    get hint() {
        if (!this.props.model.canCreate) {
            return "";
        }
        return _t("Drag over a row to book it · click a bar to open it");
    }

    get rowCountLabel() {
        const count = this.props.model.rows.length;
        return count === 1 ? _t("1 resource") : _t("%s resources", count);
    }

    /**
     * The key reads the states off the field itself, so each vertical gets
     * its own labels without the view knowing any of them.
     */
    get legend() {
        const params = this.props.model.params;
        const field = params.state && this.props.model.fields[params.state];
        const keys = (field && field.selection ? field.selection : []).map(
            ([value, label]) => ({value: value, label: label, overlay: false})
        );
        if (params.overlay) {
            keys.push({value: "overlay", label: _t("Block"), overlay: true});
        }
        return keys;
    }

    /**
     * Every row of the grouping model, plus one for whatever is booked
     * without a row. The empty ones stay: an agenda that only shows what is
     * already booked is useless the day the business starts using it.
     */
    get rows() {
        const model = this.props.model;
        const byRow = new Map(model.rows.map((row) => [row.id, []]));
        const orphans = [];

        for (const event of [...model.records, ...model.overlays]) {
            const bucket = byRow.get(event.rowId);
            if (bucket) {
                bucket.push(event);
            } else {
                orphans.push(event);
            }
        }

        const rows = model.rows.map((row) => ({
            id: row.id,
            name: row.name,
            unassigned: false,
            bars: this.layout(byRow.get(row.id) || []),
        }));

        if (orphans.length) {
            rows.push({
                id: false,
                name: _t("Unassigned"),
                unassigned: true,
                bars: this.layout(orphans),
            });
        }
        return rows;
    }

    layout(events) {
        const start = this.props.windowStart;
        const stop = this.windowStop;
        const span = this.props.columnCount;
        const drag = this.state.drag;

        return events
            .map((event) => {
                let from = event.start;
                let to = event.stop;

                // While a bar is being dragged it follows the pointer; the
                // write only happens when the pointer is released.
                if (drag && drag.mode !== "create" && drag.key === this.keyOf(event)) {
                    [from, to] = this.draggedDates(event, drag);
                }

                const left = (from.diff(start, "days").days);
                const right = (to.diff(start, "days").days);
                return {
                    key: this.keyOf(event),
                    event: event,
                    label: event.label,
                    state: event.state || "none",
                    overlay: event.overlay,
                    open: Boolean(event.open),
                    chained: Boolean(event.chained),
                    clipStart: from < start,
                    clipStop: to > stop,
                    days: Math.max(1, Math.round(to.diff(from, "days").days)),
                    left: Math.max(0, left),
                    width: Math.min(span, right) - Math.max(0, left),
                };
            })
            .filter((bar) => bar.width > 0)
            .sort((a, b) => a.left - b.left);
    }

    keyOf(event) {
        return (event.overlay ? "o" : "r") + event.id;
    }

    barStyle(bar) {
        return (
            "left: calc(var(--o-agenda-col) * " + bar.left + ");" +
            "width: calc(var(--o-agenda-col) * " + bar.width + ");"
        );
    }

    get boardStyle() {
        return "--o-agenda-cols: " + this.props.columnCount + ";";
    }

    get nowStyle() {
        const now = DateTime.local();
        const offset = now.diff(this.props.windowStart, "days").days;
        if (offset < 0 || offset > this.props.columnCount) {
            return false;
        }
        return "left: calc(var(--o-agenda-rail) + var(--o-agenda-col) * " + offset + ");";
    }

    get selection() {
        const drag = this.state.drag;
        if (!drag || drag.mode !== "create") {
            return false;
        }
        const from = Math.min(drag.from, drag.to);
        const to = Math.max(drag.from, drag.to);
        return {
            rowId: drag.rowId,
            style:
                "left: calc(var(--o-agenda-col) * " + from + ");" +
                "width: calc(var(--o-agenda-col) * " + (to - from + 1) + ");",
            label: this.rangeLabel(from, to),
        };
    }

    rangeLabel(from, to) {
        const start = this.props.windowStart.plus({days: from});
        const stop = this.props.windowStart.plus({days: to + 1});
        const days = to - from + 1;
        return start.toFormat("d LLL") + " → " + stop.toFormat("d LLL") +
            " · " + days + " " + (days === 1 ? _t("day") : _t("days"));
    }

    // ------------------------------------------------------------------
    // Pointer gestures
    // ------------------------------------------------------------------

    columnAt(trackEl, clientX) {
        const rect = trackEl.getBoundingClientRect();
        const width = rect.width / this.props.columnCount;
        const index = Math.floor((clientX - rect.left) / width);
        return Math.min(this.props.columnCount - 1, Math.max(0, index));
    }

    onTrackPointerDown(event, row) {
        if (event.button || !this.props.model.canCreate) {
            return;
        }
        if (event.target.closest(".o_agenda_bar")) {
            return;
        }
        const index = this.columnAt(event.currentTarget, event.clientX);
        this.state.drag = {
            mode: "create",
            rowId: row.id,
            from: index,
            to: index,
            origin: index,
            trackEl: event.currentTarget,
            moved: false,
        };
        event.currentTarget.setPointerCapture(event.pointerId);
        event.preventDefault();
    }

    onBarPointerDown(event, bar) {
        if (event.button || bar.overlay || !this.props.model.canWrite) {
            return;
        }
        const barRect = event.currentTarget.getBoundingClientRect();
        const offset = event.clientX - barRect.left;
        let mode = "move";
        if (offset <= HANDLE) {
            mode = "resize-start";
        } else if (offset >= barRect.width - HANDLE) {
            mode = "resize-end";
        }
        const track = event.currentTarget.closest(".o_agenda_track");
        const index = this.columnAt(track, event.clientX);
        this.state.drag = {
            mode: mode,
            key: bar.key,
            resId: bar.event.resId,
            origin: index,
            delta: 0,
            trackEl: track,
            moved: false,
        };
        track.setPointerCapture(event.pointerId);
        event.preventDefault();
        event.stopPropagation();
    }

    onPointerMove(event) {
        const drag = this.state.drag;
        if (!drag) {
            return;
        }
        const index = this.columnAt(drag.trackEl, event.clientX);
        if (drag.mode === "create") {
            drag.from = Math.min(drag.origin, index);
            drag.to = Math.max(drag.origin, index);
            drag.moved = drag.from !== drag.to;
        } else {
            const delta = index - drag.origin;
            drag.moved = drag.moved || delta !== 0;
            drag.delta = delta;
        }
    }

    draggedDates(event, drag) {
        const day = {days: drag.delta};
        if (drag.mode === "move") {
            return [event.start.plus(day), event.stop.plus(day)];
        }
        if (drag.mode === "resize-start") {
            const start = event.start.plus(day).startOf("day");
            return [start < event.stop ? start : event.stop.minus({days: 1}), event.stop];
        }
        const stop = event.stop.plus(day).startOf("day");
        return [event.start, stop > event.start ? stop : event.start.plus({days: 1})];
    }

    onPointerUp() {
        const drag = this.state.drag;
        if (!drag) {
            return;
        }
        this.state.drag = null;
        if (!drag.moved) {
            return;
        }
        if (drag.mode === "create") {
            const from = Math.min(drag.from, drag.to);
            const to = Math.max(drag.from, drag.to);
            this.props.onCreateRange(
                drag.rowId,
                this.props.windowStart.plus({days: from}),
                this.props.windowStart.plus({days: to + 1})
            );
            return;
        }
        const event = [...this.props.model.records].find(
            (record) => this.keyOf(record) === drag.key
        );
        if (event) {
            const [start, stop] = this.draggedDates(event, drag);
            this.props.onMoveRecord(event, start, stop);
        }
    }

    onPointerCancel() {
        this.state.drag = null;
    }

    onBarClick(bar) {
        if (this.state.drag) {
            return;
        }
        this.props.onOpenRecord(bar.event);
    }
}
