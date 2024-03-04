/** @odoo-module */
import { ClosePosPopup } from "@point_of_sale/app/navbar/closing_popup/closing_popup";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(ClosePosPopup.prototype, {
    setup() {
        super.setup(...arguments);
        console.log(" 120 --- SETUP .. ");

        this.rpc = useService("rpc");
        this.state.acceptGlobalInv = this.pos.config.active_facturacion_global;
    },

    // @override
    async closeSession() {
        console.log(" CLOSE SESSION ");
        if(this.state.acceptGlobalInv){
            await this.rpc('/web/dataset/call_kw/pos.session/set_option_global_inv_active',{
                model: 'pos.session',
                method: 'set_option_global_inv_active',
                kwargs: {},
                args: [this.pos.pos_session.id,this.state.acceptGlobalInv]
            });
        }
        return super.closeSession();
    },

    hasGlobalInv(){
        return this.pos.config.active_facturacion_global
    }
});


// odoo.define('l10n_mx_edi_global_invoice_40.ClosePosPopup', function (require){
// "use strict";

// var models = require('point_of_sale.models');
// const ClosePosPopup = require('point_of_sale.ClosePosPopup');
// const Registries = require('point_of_sale.Registries');

// models.load_fields('pos.config', ["active_facturacion_global"])

// const ClosePosPopupInherit = (ClosePosPopup) =>
//     class extends ClosePosPopup{

//         constructor() {
//             super(...arguments);

//             this.state.acceptGlobalInv = this.env.pos.config.active_facturacion_global;
//         }

//         //@override
//         async closeSession() {
//             await this.rpc({
//                 model: 'pos.session',
//                 method: 'set_option_global_inv_active',
//                 args: [this.env.pos.pos_session.id,this.state.acceptGlobalInv]
//             });

//             return super.closeSession();
//         }

//         hasGlobalInv(){
//             return this.env.pos.config.active_facturacion_global
//         }


//     };

//     Registries.Component.extend(ClosePosPopup, ClosePosPopupInherit)
// });