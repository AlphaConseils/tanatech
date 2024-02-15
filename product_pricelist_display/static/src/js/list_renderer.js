odoo.define('product_pricelist_display.ProductPricelistDisplay', function (require) {
'use strict';

    var ListRenderer = require('web.ListRenderer');
    var registry = require('web.field_registry');

    ListRenderer.include({
        init: function (parent, state, params){
            this._super.apply(this, arguments);
            this.pricelist_nodes = [];
        },
        _ensureColumnFields: function(columns, fields){
            _.each(columns, function(node){
                if(!fields[node.attrs.name]){
                    columns.remove(columns.indexOf(node))
                }
            })
        },
        _renderView: function () {
            var self = this;
            if(this.state.model == 'product.template' ){
                return this._super.apply(this, arguments).then(function(){
                   return Promise.all([self._renderPricelistColumns()]);
                }).then(function(){
                    const oldPagers = self.pagers;
                    let prom;
                    let tableWrapper;
                    if (self.state.count > 0 || !self.noContentHelp) {
                        self.pagers = [];
                        const orderedBy = self.state.orderedBy;
                        self.hasHandle = orderedBy.length === 0 || orderedBy[0].name === self.handleField;
                        self._computeAggregates();
                        const $table = $(
                            '<table class="o_list_table table table-sm table-hover table-striped"/>'
                        );
                        $table.toggleClass('o_list_table_grouped', self.isGrouped);
                        $table.toggleClass('o_list_table_ungrouped', !self.isGrouped);
                        const defs = [];
                        self.defs = defs;
                        if (self.isGrouped) {
                            $table.append(self._renderHeader());
                            $table.append(self._renderGroups(self.state.data));
                            $table.append(self._renderFooter());
                        } else {
                            $table.append(self._renderHeader());
                            $table.append(self._renderBody());
                            $table.append(self._renderFooter());
                        }
                        tableWrapper = Object.assign(document.createElement('div'), {
                            className: 'table-responsive',
                        });
                        tableWrapper.appendChild($table[0]);
                        delete self.defs;
                        prom = Promise.all(defs);
                    }

                    self.el.innerHTML = "";
                    self.el.classList.remove('o_list_optional_columns');
                    oldPagers.forEach(pager => pager.destroy());
                    if (tableWrapper) {
                        self.el.appendChild(tableWrapper);
                        if (document.body.contains(self.el)) {
                            self.pagers.forEach(pager => pager.on_attach_callback());
                        }
                        if (self._shouldRenderOptionalColumnsDropdown()) {
                            self.el.classList.add('o_list_optional_columns');
                            self.$('table').append(
                                $('<i class="o_optional_columns_dropdown_toggle fa fa-ellipsis-v"/>')
                            );
                            self.$el.append(self._renderOptionalColumnsDropdown());
                        }
                        if (self.selection.length) {
                            const $checked_rows = self.$('tr').filter(
                                (i, el) => self.selection.includes(el.dataset.id)
                            );
                            $checked_rows.find('.o_list_record_selector input').prop('checked', true);
                            if ($checked_rows.length === self.$('.o_data_row').length) { // all rows are checked
                                self.$('thead .o_list_record_selector input').prop('checked', true);
                            }
                        }
                    }
                    if (!self._hasContent() && !!self.noContentHelp) {
                        self._renderNoContentHelper();
                    }
                })
            }
            else{
                return this._super.apply(this, arguments)
            }

        },


        _renderPricelistColumns: function(){
            var self = this;
            return new Promise(function(resolve){
                Promise.resolve(self._buildPricelistNode()).then(function(){
                   self._insertPricelistColumns(self.columns, self.pricelist_nodes);
                }).then(function(){
                    resolve(self.columns);
                })
            })

        },
        _insertPricelistColumns: function(columns, nodes){
            var self = this;
            var field = _.filter(columns, function (col) {
                return col.attrs.name == 'product_pricelist';
            });
            if(field.length > 0){
                var index = columns.indexOf(field[0]);
                columns.splice(index, 1);
                _.each(nodes, function(nd, ind){
                    columns.splice(index + ind, 0, nd);
                })
            }

        },
        _getDisplayedPricelist: function(){
            return this._rpc({
                model: 'product.template',
                method: 'get_pricelists'
            })
        },
        _buildPricelistNode: function(){
            var self = this;
            var defs = []
            return this._getDisplayedPricelist().then(function (res) {
                self.pricelist_nodes = []

                _.each(res, function(pricelist){
                    if(pricelist.display){
                        var attrs = {modifiers: { readonly: true },name: 'pricelist_'+pricelist.id,options: "{'currency_field': 'cost_currency_id'}",readonly: "1",widget: "monetary"};
                        var node = {attrs: attrs, children: [], tag: 'field'};
                        if(self.state.fields[node.attrs.name]){
                            self.pricelist_nodes.push(node);
                        }
                        var field = {Widget: registry.get('monetary'), fieldDependencies: {}, mode: false, modifiers:{}, name: 'pricelist_'+pricelist.id,
                                optionnal:"show", options: {'currency_field': 'cost_currency_id'}, readonly:"1", views: {}, widget:"monetary"
                        };
                        if(!self.state.fieldsInfo.list[field.name]){
                            self.state.fieldsInfo.list[field.name] = field;
                        }
                    }


                });



            })
        },

    });
});

