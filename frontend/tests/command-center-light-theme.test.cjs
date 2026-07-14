const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '..');
const viewsRoot = path.join(root, 'src', 'views');
const excludedRoots = new Set(['public']);
const excludedFiles = new Set(['Login.vue']);
const darkBackground = /background(?:-color)?\s*:\s*[^;]*(?:#050510|#0f1f33|#102238|#0f172a|#172033|#1e293b)/gi;

function vueFiles(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    if (entry.isDirectory() && dir === viewsRoot && excludedRoots.has(entry.name)) return [];
    const target = path.join(dir, entry.name);
    if (entry.isDirectory()) return vueFiles(target);
    return entry.name.endsWith('.vue') && !excludedFiles.has(entry.name) ? [target] : [];
  });
}

test('authenticated content pages do not define dark background blocks', () => {
  const violations = [];
  for (const file of vueFiles(viewsRoot)) {
    const source = fs.readFileSync(file, 'utf8');
    const matches = [...source.matchAll(darkBackground)];
    for (const match of matches) {
      violations.push(`${path.relative(root, file)}: ${match[0]}`);
    }
  }
  assert.deepEqual(violations, []);
});

test('report belongs to online sales and task remains directly reachable', () => {
  const layout = fs.readFileSync(path.join(root, 'src', 'layouts', 'MainLayout.vue'), 'utf8');
  const onlineSalesStart = layout.indexOf('label: "线上销售"');
  const productStart = layout.indexOf('label: "商品经营"', onlineSalesStart);
  const onlineSalesBlock = layout.slice(onlineSalesStart, productStart);
  assert.match(onlineSalesBlock, /path:\s*['"]\/app\/report['"][^}]*label:\s*['"]经营日报['"]/s);
  assert.match(layout, /path:\s*['"]\/app\/task['"][^}]*label:\s*['"]任务管理['"]/s);
});

test('only the explicitly reworked pages opt into the command light page scope', () => {
  const targetPages = [
    'dashboard/Index.vue',
    'report/Index.vue',
    'diagnosis/Index.vue',
    'store/Index.vue',
    'product/Index.vue',
    'product/SizeWall.vue',
    'inventory/Index.vue',
    'member/Index.vue',
    'marketing/InvestmentOptimization.vue',
  ];
  const untouchedPages = [
    'task/Index.vue',
    'finance/FinanceOverview.vue',
    'hr/HrOverview.vue',
    'system/AdminDashboard.vue',
  ];

  for (const file of targetPages) {
    const source = fs.readFileSync(path.join(viewsRoot, file), 'utf8');
    assert.match(source, /class=["'][^"']*command-light-page/, `${file} must opt into the light scope`);
  }
  for (const file of untouchedPages) {
    const source = fs.readFileSync(path.join(viewsRoot, file), 'utf8');
    assert.doesNotMatch(source, /command-light-page/, `${file} must remain outside the light scope`);
  }
});

test('authenticated theme does not globally restyle every content page', () => {
  const theme = fs.readFileSync(path.join(root, 'src', 'styles', 'theme.css'), 'utf8');
  assert.doesNotMatch(theme, /\.hb-content\s+\.(?:el-card|panel|section-panel|table-panel|filter-panel|chart-panel|metric-card|stat-card|summary-card)/);
  assert.match(theme, /\.command-light-page/);
});

test('reworked pages use business-facing Chinese section labels', () => {
  const files = ['dashboard/Index.vue', 'report/Index.vue', 'diagnosis/Index.vue', 'product/SizeWall.vue'];
  const decorativeEnglish = [
    'HUABANG BUSINESS COMMAND CENTER',
    'API METRICS',
    'BOSS DAILY REPORT',
    'AI BUSINESS DIAGNOSIS',
    'AI DIAGNOSIS SUMMARY',
    'TOP 3 ACTIONS',
    'RISK RADAR',
    'SIZE WALL OPERATIONS',
    'STORE × SIZE',
  ];
  const source = files.map((file) => fs.readFileSync(path.join(viewsRoot, file), 'utf8')).join('\n');
  for (const label of decorativeEnglish) assert.equal(source.includes(label), false, `remove decorative label: ${label}`);
});

test('product summary cards collapse to two columns on mobile', () => {
  const product = fs.readFileSync(path.join(viewsRoot, 'product', 'Index.vue'), 'utf8');
  assert.match(product, /@media\s*\(max-width:\s*760px\)[\s\S]*?\.summary-row\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/);
});

test('investment optimization uses the light command surface', () => {
  const source = fs.readFileSync(path.join(viewsRoot, 'marketing', 'InvestmentOptimization.vue'), 'utf8');
  assert.doesNotMatch(source, /background:\s*var\(--ink\)/);
  assert.doesNotMatch(source, /LIFEDATA\s*·\s*本地投放决策/);
  assert.match(source, /\.ledger-cell\.verified\s*\{[^}]*background:\s*#EFF6FF/i);
});
