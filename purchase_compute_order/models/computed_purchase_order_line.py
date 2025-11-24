##############################################################################
#
#    Purchase - Computed Purchase Order Module for Odoo
#    Copyright (C) 2019-Today: La Louve (<https://cooplalouve.fr>)
#    Copyright (C) 2019-Today: Druidoo (<https://www.druidoo.io>)
#    Copyright (C) 2013-Today GRAP (http://www.grap.coop)
#    License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#    @author Druidoo
#    @author Julien WESTE
#    @author Sylvain LE GAL (https://twitter.com/legalsylvain)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from odoo import api, fields, models


class ComputedPurchaseOrderLine(models.Model):
    _description = "Computed Purchase Order Line"
    _name = "computed.purchase.order.line"
    _order = "sequence"

    _STATE = [
        ("new", "New"),
        ("up_to_date", "Up to date"),
        ("updated", "Updated"),
    ]

    # Columns section
    computed_purchase_order_id = fields.Many2one(
        "computed.purchase.order",
        "Order Reference",
        required=True,
        ondelete="cascade",
    )
    state = fields.Selection(
        _STATE,
        required=True,
        readonly=True,
        default="new",
        help="Shows if the product's information has been updated",
    )
    sequence = fields.Integer(
        help="""Gives the sequence order when displaying a list of"""
        """ purchase order lines."""
    )
    product_id = fields.Many2one(
        "product.product",
        required=True,
        domain=[("purchase_ok", "=", True)],
    )
    uom_id = fields.Many2one(related="product_id.uom_id")
    product_sequence = fields.Integer(
        string="Product Sequence",
        related="product_id.sequence",
    )
    psi_id = fields.Many2one(
        comodel_name="product.supplierinfo",
        ondelete="set null",
    )
    product_code = fields.Char(
        "Supplier Product Code",
        related="psi_id.product_code",
    )
    product_name = fields.Char(
        "Supplier Product Name",
        related="psi_id.product_name",
    )
    product_price = fields.Float(
        "Supplier Product Price",
        compute="_compute_product_price",
    )
    discount = fields.Float(
        related="psi_id.discount",
    )
    price_policy = fields.Selection(
        related="psi_id.price_policy",
    )
    subtotal = fields.Float(
        compute="_compute_subtotal_price",
        digits="Product Price",
    )
    product_packaging_id = fields.Many2one(
        "product.packaging",
        string="Packaging",
        domain="[('product_id', '=', product_id)]",
    )
    package_qty = fields.Float(
        related="product_packaging_id.qty",
        string="Package Quantity",
        store=True,
    )
    weight = fields.Float(
        related="product_id.weight",
        string="Net Weight",
    )
    uom_po_id = fields.Many2one(
        related="psi_id.product_uom",
    )
    average_consumption = fields.Float(
        compute="_compute_average_consumption",
        digits=(12, 3),
    )
    displayed_average_consumption = fields.Float(
        digits=(12, 3),
    )
    consumption_range = fields.Integer(
        "Range (days)",
        help="""Range (in days) used to display the average
        consumption""",
    )
    stock_duration = fields.Float(
        compute="_compute_stock_duration",
        string="Stock Duration (Days)",
        help="Number of days the stock should last.",
    )
    virtual_duration = fields.Float(
        compute="_compute_stock_duration",
        string="Virtual Duration (Days)",
        help="Number of days the stock should last after the purchase.",
    )
    purchase_qty_package = fields.Float(
        string="Number of packages",
        help="""The number of packages you'll buy.""",
    )
    purchase_qty = fields.Float(
        string="Quantity to purchase",
        compute="_compute_purchase_qty",
        readonly=False,
        store=True,
        help="The quantity you should purchase.",
    )
    manual_input_output_qty = fields.Float(
        string="Manual variation",
        default=0,
        help="""Write here some extra quantity depending of some"""
        """ input or output of products not entered in the software\n"""
        """- negative quantity : extra output ; \n"""
        """- positive quantity : extra input.""",
    )
    qty_available = fields.Float(
        compute="_compute_qty",
        string="On Hand Quantity",
        help="The available quantity on hand for this product",
    )
    incoming_qty = fields.Float(
        compute="_compute_qty",
        string="Incoming Quantity",
        help="Virtual incoming entries",
    )
    outgoing_qty = fields.Float(
        compute="_compute_qty",
        string="Outgoing Quantity",
        help="Virtual outgoing entries",
    )
    virtual_qty = fields.Float(
        compute="_compute_qty",
        string="Virtual Quantity",
        help="Quantity on hand + Virtual incoming and outgoing entries",
    )
    computed_qty = fields.Float(
        compute="_compute_computed_qty",
        string="Stock",
        help="The sum of all quantities selected.",
        digits="Product UoM",
    )
    cpo_state = fields.Selection(
        string="CPO State",
        related="computed_purchase_order_id.state",
    )
    shelf_life = fields.Integer(
        string="Shelf life (days)",
        related="psi_id.shelf_life",
        store=True,
    )

    # Constraints section
    _sql_constraints = [
        (
            "product_id_uniq",
            "unique(computed_purchase_order_id,product_id)",
            "Product must be unique by computed purchase order!",
        ),
    ]

    @api.onchange("product_packaging_id")
    def onchange_product_packaging_id(self):
        self.purchase_qty_package = 0
        self.purchase_qty = 0
        if not self.product_packaging_id:
            self.psi_id = False
        else:
            valid_psi = self.env["product.supplierinfo"].search(
                [
                    ("product_tmpl_id", "=", self.product_id.product_tmpl_id.id),
                    ("product_packaging_id", "=", self.product_packaging_id.id),
                    ("partner_id", "=", self.computed_purchase_order_id.partner_id.id),
                ],
                limit=1,
                order="sequence asc",
            )
            self.psi_id = valid_psi.id

    @api.depends("purchase_qty_package", "product_packaging_id.qty")
    def _compute_purchase_qty(self):
        for cpol in self:
            if (
                cpol.purchase_qty_package
                and int(cpol.purchase_qty_package) == cpol.purchase_qty_package
            ):
                cpol.purchase_qty = cpol.package_qty * cpol.purchase_qty_package
            else:
                cpol.purchase_qty = cpol.purchase_qty

    @api.depends("psi_id.price", "psi_id.base_price", "price_policy")
    def _compute_product_price(self):
        for line in self:
            if line.price_policy == "package":
                line.product_price = line.psi_id.base_price
            else:
                line.product_price = line.psi_id.price

    @api.depends(
        "purchase_qty",
        "purchase_qty_package",
        "product_price",
        "price_policy",
    )
    def _compute_subtotal_price(self):
        for line in self:
            net_unit_price = line.product_price * (1 - line.discount / 100.0)
            if line.price_policy == "package":
                line.subtotal = line.purchase_qty_package * net_unit_price
            else:
                line.subtotal = line.purchase_qty * net_unit_price

    @api.depends("displayed_average_consumption", "consumption_range")
    def _compute_average_consumption(self):
        for line in self:
            line.average_consumption = (
                line.consumption_range
                and line.displayed_average_consumption / line.consumption_range
                or 0
            )

    # Fields Function section
    @api.depends("product_id")
    def _compute_qty(self):
        for cpol in self:
            cpol.qty_available = cpol.product_id.qty_available
            cpol.incoming_qty = cpol.product_id.incoming_qty
            cpol.outgoing_qty = cpol.product_id.outgoing_qty
            cpol.virtual_qty = (
                cpol.qty_available + cpol.incoming_qty - cpol.outgoing_qty
            )

    @api.depends(
        "qty_available", "incoming_qty", "outgoing_qty", "computed_purchase_order_id"
    )
    def _compute_computed_qty(self):
        for cpol in self:
            computed_qty = cpol.qty_available
            if cpol.computed_purchase_order_id.compute_pending_quantity:
                computed_qty += cpol.incoming_qty - cpol.outgoing_qty
            cpol.computed_qty = computed_qty

    @api.depends(
        "purchase_qty",
        "average_consumption",
        "computed_qty",
        "manual_input_output_qty",
    )
    def _compute_stock_duration(self):
        for cpol in self:
            cpol.stock_duration = 0
            cpol.virtual_duration = 0
            if cpol.product_id:
                if cpol.average_consumption != 0:
                    cpol.stock_duration = (
                        cpol.computed_qty + cpol.manual_input_output_qty
                    ) / cpol.average_consumption
                    cpol.virtual_duration = (
                        cpol.computed_qty
                        + cpol.manual_input_output_qty
                        + cpol.purchase_qty
                    ) / cpol.average_consumption

    def unlink_psi(self):
        psi_obj = self.env["product.supplierinfo"]
        for cpol in self:
            cpo = cpol.computed_purchase_order_id
            partner_id = cpo.partner_id.id
            product_tmpl_id = cpol.product_id.product_tmpl_id.id
            domain_psi = [
                ("partner_id", "=", partner_id),
                ("product_tmpl_id", "=", product_tmpl_id),
            ]
            if cpol.product_packaging_id:
                domain_psi.append(
                    ("product_packaging_id", "=", cpol.product_packaging_id.id)
                )
            psi_ids = psi_obj.search(domain_psi)
            psi_ids.unlink()
            cpol.unlink()

    def create_psi(self):
        psi_obj = self.env["product.supplierinfo"]
        psi_ids = []
        for cpol in self:
            cpo = cpol.computed_purchase_order_id
            partner_id = cpo.partner_id.id
            product_tmpl_id = cpol.product_id.product_tmpl_id.id
            vals = {
                "partner_id": partner_id,
                "product_name": cpol.product_name,
                "product_code": cpol.product_code,
                "product_uom": cpol.uom_po_id.id,
                "product_packaging_id": cpol.product_packaging_id.id,
                "min_qty": cpol.package_qty,
                "product_id": product_tmpl_id,
                "price_policy": cpol.price_policy,
            }
            psi_ids.append(psi_obj.create(vals).id)
            cpol.state = "up_to_date"
        return psi_ids

    def action_view_computed_purchase_order_line(self):
        self.ensure_one()
        res_id = self.env.ref(
            "purchase_compute_order.view_computed_purchase_order_line_form"
        ).id
        return {
            "type": "ir.actions.act_window",
            "name": "Computed Purchase Order Line",
            "view_mode": "form",
            "res_model": "computed.purchase.order.line",
            "views": [(res_id, "form")],
            "view_id": res_id,
            "target": "current",
            "res_id": self.id,
        }
