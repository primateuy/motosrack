/** @odoo-module **/

import {AgendaArchParser} from "./agenda_arch_parser.esm";
import {AgendaController} from "./agenda_controller.esm";
import {AgendaModel} from "./agenda_model.esm";
import {AgendaRenderer} from "./agenda_renderer.esm";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";

export const agendaView = {
    type: "agenda",
    display_name: _t("Agenda"),
    icon: "fa fa-calendar-o",
    multiRecord: true,
    ArchParser: AgendaArchParser,
    Controller: AgendaController,
    Model: AgendaModel,
    Renderer: AgendaRenderer,
    searchMenuTypes: ["filter", "favorite"],

    props: (genericProps, view) => {
        const {arch, fields, resModel} = genericProps;
        const archInfo = new view.ArchParser().parse(arch, fields);
        return {
            ...genericProps,
            modelParams: {...archInfo, resModel: resModel, fields: fields},
            Model: view.Model,
        };
    },
};

registry.category("views").add("agenda", agendaView);
