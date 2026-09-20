from leasedd.financial_presentation import source_layout


def test_layout_retains_order_sections_and_plain_cells_without_executing_markup():
    first='<tr><td>货币资金</td><td>100</td><td>80</td></tr>'
    second='<tr><td>资本公积</td><td>50</td><td>40</td></tr>'
    md='# 合并资产负债表\n<table><tr><td>流动资产：</td><td></td><td></td></tr>'+first+'<tr><td>所有者权益：</td><td></td><td></td></tr>'+second+'</table>'
    layout=source_layout(md)
    assert layout[first][0]['source_section']=='流动资产'
    assert layout[second][0]['source_section']=='所有者权益'
    assert layout[first][0]['source_order']<layout[second][0]['source_order']
    assert layout[first][0]['source_cells']==['货币资金','100','80']
    assert layout[first][0]['source_start_line']==2


def test_layout_does_not_treat_numeric_zero_as_a_section_heading():
    row='<tr><td>存货</td><td>0</td><td>0</td></tr>'
    md='# 合并资产负债表\n<table>'+row+'</table>'
    assert source_layout(md)[row][0]['source_section']=='资产负债表'
