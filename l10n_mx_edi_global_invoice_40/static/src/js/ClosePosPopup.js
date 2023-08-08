odoo.define('l10n_mx_edi_global_invoice_40.ClosePosPopup', function (require){
"use strict";

var models = require('point_of_sale.models');
const ClosePosPopup = require('point_of_sale.ClosePosPopup');
const NumberBuffer = require('point_of_sale.NumberBuffer');
var exports = require("point_of_sale.models");
const { useState, useRef } = owl.hooks;
const AbstractAwaitablePopup = require('point_of_sale.AbstractAwaitablePopup');
const Registries = require('point_of_sale.Registries');
const { identifyError } = require('point_of_sale.utils');
const { ConnectionLostError, ConnectionAbortedError} = require('@web/core/network/rpc_service')

models.load_fields('pos.config', ["active_facturacion_global"])

const ClosePosPopupInherit = (ClosePosPopup) =>
    class extends ClosePosPopup{

        constructor() {
            super(...arguments);

            this.state.acceptGlobalInv = this.env.pos.config.active_facturacion_global;
        }

        //@override
        async closeSession() {
            await this.rpc({
                model: 'pos.session',
                method: 'set_option_global_inv_active',
                args: [this.env.pos.pos_session.id,this.state.acceptGlobalInv]
            });

            return super.closeSession();
        }

        hasGlobalInv(){
            return this.env.pos.config.active_facturacion_global
        }


    };

    Registries.Component.extend(ClosePosPopup, ClosePosPopupInherit)
});