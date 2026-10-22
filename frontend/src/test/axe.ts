import axe from 'axe-core';

/** Runs axe on a node and returns serious/critical violations as readable strings (color-contrast and region are checked separately). */
export async function axeCheck(node: Element): Promise<string[]> {
  const res = await axe.run(node, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
  return res.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical' || v.impact === 'moderate')
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
}
