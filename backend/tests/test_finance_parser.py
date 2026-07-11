import json

from app.modules.dingtalk.sync.finance_parser import extract_amount


def test_extract_amount_reads_nested_reimbursement_table_rows():
    form_values = [{
        "component_type": "DDBizSuite",
        "value": json.dumps([{
            "rowValue": [
                {"label": "店铺名称", "value": "285204"},
                {"label": "报销金额(元)", "value": "402.43"},
            ]
        }], ensure_ascii=False),
    }]

    assert extract_amount(form_values) == 402.43


def test_extract_amount_sums_multiple_nested_detail_rows():
    form_values = [{
        "name": "报销明细",
        "value": json.dumps([
            {"rowValue": [{"label": "报销金额(元)", "value": "100"}]},
            {"rowValue": [{"label": "报销金额(元)", "value": "200.50"}]},
        ], ensure_ascii=False),
    }]

    assert extract_amount(form_values) == 300.50
