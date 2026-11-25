import {element} from './client.js';

function block(target,className,content) {
  const node=element('div',content,{class:className});
  target.append(node);
  return node;
}

export function visualize(report,selected) {
  const target=document.querySelector('#visual');
  target.replaceChildren();
  const measurement=report.cases?.find(row=>row.case===selected)?.measure;
  if (!measurement) {block(target,'chart-note','选择有计算值的分组');return;}
  const e=measurement.evidence;

  const wires=block(target,'grade-wires');
  for(const [field,grade] of Object.entries(e.grades)) {
    const row=block(wires,'grade-wire'); block(row,'field-key',`字段 ${field}`);
    for(let n=0;n<=3;n++) block(row,n===grade?'grade-node active':'grade-node',`${n} 级`);
    if(e.approved.includes(Number(field))) block(row,'permit','已批准');
  }
}
