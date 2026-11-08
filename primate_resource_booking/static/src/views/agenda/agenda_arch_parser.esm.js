/** @odoo-module **/

/**
 * Reads the <agenda> arch.
 *
 * The view is generic: it only knows that something occupies a row between
 * two dates. Which field holds the row, the dates, the label or the state is
 * declared here, so a vertical gets its own agenda without touching this
 * code.
 */

import {_t} from "@web/core/l10n/translation";
import {visitXML} from "@web/core/utils/xml";

export class AgendaArchParseError extends Error {}

export class AgendaArchParser {
    parse(arch, fields) {
        const info = {
            fieldNames: [],
            rowLimit: 200,
            overlay: false,
        };

        visitXML(arch, (node) => {
            if (node.tagName !== "agenda") {
                return;
            }
            for (const required of ["date_start", "date_stop", "group_by"]) {
                if (!node.hasAttribute(required)) {
                    throw new AgendaArchParseError(
                        _t("The agenda view needs a '%s' attribute.", required)
                    );
                }
            }

            info.dateStart = node.getAttribute("date_start");
            info.dateStop = node.getAttribute("date_stop");
            info.groupBy = node.getAttribute("group_by");
            info.label = node.getAttribute("label") || "display_name";
            info.state = node.getAttribute("state") || false;
            info.chain = node.getAttribute("chain") || false;
            info.rowDomain = node.getAttribute("group_domain") || "[]";
            info.rowOrder = node.getAttribute("group_order") || false;
            info.className = node.getAttribute("class") || "";
            if (node.hasAttribute("group_limit")) {
                info.rowLimit = Number(node.getAttribute("group_limit"));
            }

            const groupField = fields[info.groupBy];
            if (!groupField || groupField.type !== "many2one") {
                throw new AgendaArchParseError(
                    _t("'group_by' must be a many2one field, got '%s'.", info.groupBy)
                );
            }
            info.rowModel = groupField.relation;

            // Blocks, maintenance, anything from another model that takes the
            // same row without being a record of this view's model.
            if (node.hasAttribute("overlay_model")) {
                info.overlay = {
                    resModel: node.getAttribute("overlay_model"),
                    dateStart: node.getAttribute("overlay_date_start") || "start",
                    dateStop: node.getAttribute("overlay_date_stop") || "stop",
                    groupBy: node.getAttribute("overlay_group_by") || info.groupBy,
                    label: node.getAttribute("overlay_label") || "display_name",
                    domain: node.getAttribute("overlay_domain") || "[]",
                };
            }

            const names = new Set([
                info.dateStart,
                info.dateStop,
                info.groupBy,
                info.label,
            ]);
            if (info.state) {
                names.add(info.state);
            }
            if (info.chain) {
                names.add(info.chain);
            }
            info.fieldNames = [...names].filter((name) => name in fields);
        });

        if (!info.dateStart) {
            throw new AgendaArchParseError(_t("No <agenda> node in the view."));
        }
        return info;
    }
}
