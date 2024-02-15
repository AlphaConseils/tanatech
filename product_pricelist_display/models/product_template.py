# -*- coding: utf-8 -*
from odoo import api, fields, models
import collections
import contextlib


class ProdcutTemplate(models.Model):
    _inherit = 'product.template'

    product_pricelist = fields.Char('Product Pricelist')

    @api.model
    def get_pricelists(self):
        """
        Get pricelists which we want to display in product list
        :return: dict : dictionary with pricelist id and name
        """
        pricelists = self.env['product.pricelist'].search([])
        result = list()
        for pricelist in pricelists:
            values = {'id': pricelist.id, 'name': pricelist.name, 'display': pricelist.display_in_products}
            result.append(values)
        return result

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        """
            Add dynamic pricelist fields
        :param allfields:
        :param attributes:
        :return:
        """
        res = super(ProdcutTemplate, self).fields_get(allfields, attributes)
        pricelists = self.get_pricelists()
        for pricelist in pricelists:
            values = {'name': 'pricelist_' + str(pricelist.get('id')),
                      'type': 'float',
                      'string': pricelist.get('name'),
                      'exportable': True,
                      'selectable': True,
                      'searchable': False}
            res['pricelist_' + str(pricelist.get('id'))] = values
        return res

    def read(self, fields=None, load='_classic_read'):
        """
            Add dynamic price value of pricelist we want to display
        :param fields:
        :param load:
        :return:
        """
        fields = list(filter(lambda f: f in self._fields.keys(), fields))
        res = super(ProdcutTemplate, self).read(fields, load)
        if self._context.get('readPricelist', False):
            pricelists = self.get_pricelists()
            pricelist_obj = self.env['product.pricelist']
            product_tmpl_obj = self.env['product.template']
            for values in res:
                if 'id' in values.keys():
                    record = product_tmpl_obj.browse(values.get('id'))
                    for pricelist in pricelists:
                        pricelist = pricelist_obj.browse(pricelist.get('id'))
                        price = pricelist.price_get(record.product_variant_id.id, 1)
                        values['pricelist_'+str(pricelist.id)] = price.get(pricelist.id)
        return res

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        fields = list(filter(lambda f: f in self._fields.keys(), fields))
        return super(ProdcutTemplate, self).read_group(domain, fields, groupby, offset, limit, orderby, lazy)

    def _update_cache(self, values, validate=True):
        values = values.items()
        values = [val for val in values if val[0] in self._fields]
        values = dict(values)
        super(ProdcutTemplate, self)._update_cache(values, validate)

    def _export_rows(self, fields, *, _is_toplevel_call=True):
        """ Export fields of the records in ``self``.

            :param fields: list of lists of fields to traverse
            :param bool _is_toplevel_call:
                used when recursing, avoid using when calling from outside
            :return: list of lists of corresponding values
        """
        import_compatible = self.env.context.get('import_compat', True)
        lines = []

        def splittor(rs):
            """ Splits the self recordset in batches of 1000 (to avoid
            entire-recordset-prefetch-effects) & removes the previous batch
            from the cache after it's been iterated in full
            """
            for idx in range(0, len(rs), 1000):
                sub = rs[idx:idx+1000]
                for rec in sub:
                    yield rec
                rs.invalidate_cache(ids=sub.ids)
        if not _is_toplevel_call:
            splittor = lambda rs: rs

        # memory stable but ends up prefetching 275 fields (???)
        for record in splittor(self):
            # main line of record, initially empty
            current = [''] * len(fields)
            lines.append(current)

            # list of primary fields followed by secondary field(s)
            primary_done = []

            # process column by column
            for i, path in enumerate(fields):
                if not path:
                    continue

                name = path[0]
                if name in primary_done:
                    continue

                if name == '.id':
                    current[i] = str(record.id)
                elif name == 'id':
                    current[i] = (record._name, record.id)
                else:
                    try:
                        field = record._fields[name]
                        value = record[name]
                    except KeyError:
                        modal_name = record._name
                        if modal_name == 'product.template':
                        # code here
                            pricelists = record.get_pricelists()
                            res = dict()
                            for pricelist in pricelists:
                                values = {'name': 'pricelist_' + str(pricelist.get('id')),
                                          'type': 'float',
                                          'string': pricelist.get('name'),
                                          'exportable': True,
                                          'selectable': True,
                                          'searchable': True}

                            res['pricelist_' + str(pricelist.get('id'))] = values

                            fields_value = record.read(fields=res)[0]
                            value = fields_value[name]

                    # this part could be simpler, but it has to be done this way
                    # in order to reproduce the former behavior
                    if not isinstance(value, models.BaseModel):
                        current[i] = field.convert_to_export(value, record)
                    else:
                        primary_done.append(name)
                        # recursively export the fields that follow name; use
                        # 'display_name' where no subfield is exported
                        fields2 = [(p[1:] or ['display_name'] if p and p[0] == name else [])
                                   for p in fields]

                        # in import_compat mode, m2m should always be exported as
                        # a comma-separated list of xids or names in a single cell
                        if import_compatible and field.type == 'many2many':
                            index = None
                            # find out which subfield the user wants & its
                            # location as we might not get it as the first
                            # column we encounter
                            for name in ['id', 'name', 'display_name']:
                                with contextlib.suppress(ValueError):
                                    index = fields2.index([name])
                                    break
                            if index is None:
                                # not found anything, assume we just want the
                                # name_get in the first column
                                name = None
                                index = i

                            if name == 'id':
                                xml_ids = [xid for _, xid in value.__ensure_xml_id()]
                                current[index] = ','.join(xml_ids)
                            else:
                                current[index] = field.convert_to_export(value, record)
                            continue

                        lines2 = value._export_rows(fields2, _is_toplevel_call=False)
                        if lines2:
                            # merge first line with record's main line
                            for j, val in enumerate(lines2[0]):
                                if val or isinstance(val, (int, float)):
                                    current[j] = val
                            # append the other lines at the end
                            lines += lines2[1:]
                        else:
                            current[i] = ''

        # if any xid should be exported, only do so at toplevel
        if _is_toplevel_call and any(f[-1] == 'id' for f in fields):
            bymodels = collections.defaultdict(set)
            xidmap = collections.defaultdict(list)
            # collect all the tuples in "lines" (along with their coordinates)
            for i, line in enumerate(lines):
                for j, cell in enumerate(line):
                    if type(cell) is tuple:
                        bymodels[cell[0]].add(cell[1])
                        xidmap[cell].append((i, j))
            # for each model, xid-export everything and inject in matrix
            for model, ids in bymodels.items():
                for record, xid in self.env[model].browse(ids).__ensure_xml_id():
                    for i, j in xidmap.pop((record._name, record.id)):
                        lines[i][j] = xid
            assert not xidmap, "failed to export xids for %s" % ', '.join('{}:{}' % it for it in xidmap.items())

        return lines