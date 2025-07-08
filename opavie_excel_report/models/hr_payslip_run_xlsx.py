from odoo import models, _

def add_zeros(str_value, length):
    """
        Add zero to value according specific length
    :param str_value:
    :param length:
    :return:
    """
    zeros_to_add = length - len(str_value)
    str_value = "0" * zeros_to_add + str_value
    return str_value


def float_to_string(float_num):
    """
        Cast float to string
    :param float_num:
    :return:
    """
    num_str = str(float_num)
    num_str = num_str.replace(".", "")
    return num_str


class HrPayslipXlsx(models.AbstractModel):
    _name = "report.opavie_excel_report.report_opavie_xlsx"
    _inherit = "report.report_xlsx.abstract"

    def generate_xlsx_report(self, workbook, data, lines):
        """
            Generate opavi report
        :param workbook:
        :param data:
        :param lines:
        """
        report_name = "Salaire" + " " + lines.date_start.strftime("%m%y")

        title_body = workbook.add_format({"align": "center", "border": 1})
        total = 0
        for value in lines.slip_ids:
            net_salary_line = value.line_ids
            net_salary = net_salary_line[-1].total if net_salary_line else 0
            net_salary = round(net_salary)
            total += net_salary
        total_display = round(total)
        total_net = add_zeros(str(f"{total_display:.2f}").replace(".", ""), 12)
        sheet = workbook.add_worksheet("OPAVI report")
        sheet.set_column(0, 0, 10)
        sheet.set_column(0, 1, 43)
        sheet.set_column(0, 2, 43)
        sheet.set_column(0, 3, 43)

        # if self.env.company.name.lower().startswith("jara distribution"):
        #     sheet.write(0, 0, _("00005000067069530000113"), title_body)
        #     sheet.write(0, 1, _(total_net), title_body)
        #     sheet.write(0, 2, _("V00612"), title_body)
        #     sheet.write(0, 3, _(report_name), title_body)
        # elif self.env.company.name.lower().startswith("societe de gestion"):
        #     sheet.write(0, 0, _("00005000067076067000154"), title_body)
        #     sheet.write(0, 1, _(total_net), title_body)
        #     sheet.write(0, 2, _("V00611"), title_body)
        #     sheet.write(0, 3, _(report_name), title_body)
        # elif self.env.company.name.lower().startswith("biskot"):
        #     sheet.write(0, 0, _("00005000067251439000165"), title_body)
        #     sheet.write(0, 1, _(total_net), title_body)
        #     sheet.write(0, 2, _("V00721"), title_body)
        #     sheet.write(0, 3, _(report_name), title_body)
        company_acc_number = (
            add_zeros(self.env.company.company_account_number.replace(" ", ""), 23)
            if self.env.company.company_account_number
            else " "
        )
        transfer_code = self.env.company.transfer_code or " "
        sheet.write(0, 0, company_acc_number, title_body)
        sheet.write(0, 1, _(total_net), title_body)
        sheet.write(0, 2, transfer_code, title_body)
        sheet.write(0, 3, _(report_name), title_body)
        for index, value in enumerate(lines.slip_ids):
            employee_bank_account = (
                add_zeros(value.employee_id.bank_account_id.acc_number.replace(" ", ""), 23)
                if value.employee_id.bank_account_id.acc_number
                else " "
            )
            net_to_pay_line = value.line_ids
            if net_to_pay_line:
                net_to_pay_float = net_to_pay_line[-1].total
                net_to_pay = round(net_to_pay_float)
                employee_salary = add_zeros(
                    str(f"{net_to_pay:.2f}").replace(".", ""), 12
                )
            else:
                employee_salary = "0"
            employee_matricule = (
                value.employee_id.registration_number if value.employee_id.registration_number else " "
            )
            employee_name = value.employee_id.name if value.employee_id.name else " "
            sheet.write(index + 1, 0, employee_bank_account, title_body)
            sheet.write(index + 1, 1, employee_salary, title_body)
            sheet.write(index + 1, 2, employee_matricule, title_body)
            sheet.write(index + 1, 3, employee_name, title_body)
