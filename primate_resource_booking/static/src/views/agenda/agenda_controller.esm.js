/** @odoo-module **/

/**
 * Holds what the operator sees: which window, how tall the rows are and how
 * the bars are drawn. The three preferences are remembered per browser, so
 * everyone works the way they like without a setting to maintain.
 */

import {Component, onWillStart, useRef, useState} from "@odoo/owl";
import {FormViewDialog} from "@web/views/view_dialogs/form_view_dialog";
import {Layout} from "@web/search/layout";
import {SearchBar} from "@web/search/search_bar/search_bar";
import {_t} from "@web/core/l10n/translation";
import {browser} from "@web/core/browser/browser";
import {serializeDateTime} from "@web/core/l10n/dates";
import {standardViewProps} from "@web/views/standard_view_props";
import {useModel} from "@web/model/model";
import {useSearchBarToggler} from "@web/search/search_bar/search_bar_toggler";
import {useService} from "@web/core/utils/hooks";
import {useSetupAction} from "@web/search/action_hook";

import {AgendaRenderer} from "./agenda_renderer.esm";

const {DateTime} = luxon;

const SCALES = {week: 7, fortnight: 15, month: 31};
const DENSITIES = ["compact", "cozy", "roomy"];
const VARIANTS = ["soft", "solid", "minimal"];
const STORAGE_KEY = "primate_agenda_preferences";

export class AgendaController extends Component {
    static template = "primate_resource_booking.AgendaView";
    static components = {Layout, SearchBar, AgendaRenderer};
    static props = {
        ...standardViewProps,
        modelParams: Object,
        Model: Function,
    };

    setup() {
        this.rootRef = useRef("root");
        this.model = useModel(this.props.Model, this.props.modelParams);
        useSetupAction({rootRef: this.rootRef});
        this.searchBarToggler = useSearchBarToggler();
        this.dialog = useService("dialog");
        this.notification = useService("notification");

        this.state = useState({
            scale: "fortnight",
            density: "cozy",
            variant: "soft",
            anchor: DateTime.local().startOf("day").minus({days: 4}),
            ...this.restorePreferences(),
        });

        onWillStart(() => this.model.setWindow(this.state.anchor, this.windowStop));
    }

    // ------------------------------------------------------------------
    // Preferences
    // ------------------------------------------------------------------

    restorePreferences() {
        try {
            const saved = JSON.parse(browser.localStorage.getItem(STORAGE_KEY) || "{}");
            const preferences = {};
            if (saved.scale in SCALES) {
                preferences.scale = saved.scale;
            }
            if (DENSITIES.includes(saved.density)) {
                preferences.density = saved.density;
            }
            if (VARIANTS.includes(saved.variant)) {
                preferences.variant = saved.variant;
            }
            return preferences;
        } catch {
            // No storage, or something else wrote there: the defaults do.
            return {};
        }
    }

    savePreferences() {
        try {
            browser.localStorage.setItem(
                STORAGE_KEY,
                JSON.stringify({
                    scale: this.state.scale,
                    density: this.state.density,
                    variant: this.state.variant,
                })
            );
        } catch {
            // Nothing to save: the choice lasts for this visit.
        }
    }

    // ------------------------------------------------------------------
    // Window
    // ------------------------------------------------------------------

    get columnCount() {
        return SCALES[this.state.scale];
    }

    get windowStop() {
        return this.state.anchor.plus({days: this.columnCount});
    }

    get periodLabel() {
        const start = this.state.anchor;
        const stop = this.windowStop.minus({days: 1});
        if (start.hasSame(stop, "month")) {
            return start.toFormat("LLLL yyyy");
        }
        return start.toFormat("LLL") + " – " + stop.toFormat("LLL yyyy");
    }

    async moveWindow(anchor) {
        this.state.anchor = anchor;
        await this.model.setWindow(anchor, this.windowStop);
    }

    onPrevious() {
        return this.moveWindow(
            this.state.anchor.minus({days: Math.ceil(this.columnCount / 2)})
        );
    }

    onNext() {
        return this.moveWindow(
            this.state.anchor.plus({days: Math.ceil(this.columnCount / 2)})
        );
    }

    onToday() {
        return this.moveWindow(
            DateTime.local().startOf("day").minus({days: Math.floor(this.columnCount / 3)})
        );
    }

    onScale(scale) {
        this.state.scale = scale;
        this.savePreferences();
        return this.model.setWindow(this.state.anchor, this.windowStop);
    }

    onDensity(density) {
        this.state.density = density;
        this.savePreferences();
    }

    onVariant(variant) {
        this.state.variant = variant;
        this.savePreferences();
    }

    // ------------------------------------------------------------------
    // Records
    // ------------------------------------------------------------------

    get rendererProps() {
        return {
            model: this.model,
            scale: this.state.scale,
            density: this.state.density,
            variant: this.state.variant,
            windowStart: this.state.anchor,
            columnCount: this.columnCount,
            onCreateRange: this.onCreateRange.bind(this),
            onOpenRecord: this.onOpenRecord.bind(this),
            onMoveRecord: this.onMoveRecord.bind(this),
        };
    }

    /**
     * A range marked on a row opens the quick-create form of the vertical,
     * which is the one named by `form_view_ref` in the action's context.
     */
    onCreateRange(rowId, start, stop) {
        const params = this.props.modelParams;
        const context = {
            ...this.props.context,
            ["default_" + params.dateStart]: serializeDateTime(start),
            ["default_" + params.dateStop]: serializeDateTime(stop),
        };
        if (rowId) {
            context["default_" + params.groupBy] = rowId;
        }
        this.dialog.add(FormViewDialog, {
            resModel: this.props.resModel,
            context: context,
            title: _t("New booking"),
            onRecordSaved: () => this.model.load(),
        });
    }

    onOpenRecord(event) {
        this.dialog.add(FormViewDialog, {
            resModel: event.overlay ? event.resModel : this.props.resModel,
            resId: event.resId,
            context: this.props.context,
            onRecordSaved: () => this.model.load(),
        });
    }

    async onMoveRecord(event, start, stop) {
        try {
            await this.model.writeDates(event.resId, start, stop);
        } catch (error) {
            // A refused move is normal here: two bookings of the same
            // resource may not overlap. Put the bar back and say why.
            await this.model.load();
            this.notification.add(
                error.data && error.data.message ? error.data.message : _t("The booking could not be moved."),
                {type: "warning"}
            );
        }
    }
}
