odoo.define('product_pricelist_display.BasicModel', function (require) {
'use strict';

    var BasicModel = require('web.BasicModel');

    BasicModel.include({
        _load: function (dataPoint, options) {
            var context = {readPricelist: true}
            if(dataPoint.type === 'list' && dataPoint.model === 'product.template'){
                dataPoint.context = _.extend({}, dataPoint.context, context);
            }
            return this._super.apply(this, arguments)
        },


    });

});

