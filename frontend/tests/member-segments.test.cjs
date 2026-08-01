const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const source = fs.readFileSync(path.resolve(__dirname, '../src/views/member/Index.vue'), 'utf8')
const api = fs.readFileSync(path.resolve(__dirname, '../src/api/member.ts'), 'utf8')

test('member page exposes segment risk and wakeup views', () => {
  assert.match(source, /label="会员分层"/)
  assert.match(source, /label="风险名单"/)
  assert.match(source, /label="唤醒名单"/)
  assert.match(source, /待确认责任人/)
  assert.match(source, /数据证据/)
  assert.match(api, /\/member\/segments\/overview/)
  assert.match(api, /\/member\/segments\/list/)
  assert.match(api, /\/member\/segments\/risks/)
  assert.match(api, /\/member\/segments\/wakeups/)
})

test('sensitive export is permission gated and the content stays light', () => {
  assert.match(source, /member:sensitive:export/)
  assert.match(source, /canExportSensitive/)
  assert.doesNotMatch(source, /background:\s*#0[fF]172[aA]/)
  assert.doesNotMatch(source, /background:\s*#0[bB]1[fF]33/)
})

test('member asset tabs and values require sensitive member permission', () => {
  assert.match(source, /member:sensitive:view/)
  assert.match(source, /canViewSensitiveMembers/)
  assert.match(source, /v-if="canViewSensitiveMembers"/)
  assert.match(source, /sensitive_redacted/)
  assert.doesNotMatch(source, /Promise\.all\(\[memberApi\.getOverview\(\), memberApi\.getAssetOverview\(\)\]\)/)
  assert.match(source, /if \(canViewSensitiveMembers\.value\)[\s\S]*memberApi\.getAssetOverview\(\)/)
})

test('segment views and requests require the segment view permission', () => {
  assert.match(source, /const canViewSegments = computed\(\(\) => authStore\.hasPermission\("member:segment:view"\)\)/)
  assert.match(source, /<el-tab-pane v-if="canViewSegments" label="会员分层"/)
  assert.match(source, /<el-tab-pane v-if="canViewSegments" label="风险名单"/)
  assert.match(source, /<el-tab-pane v-if="canViewSegments" label="唤醒名单"/)
  assert.match(source, /if \(!canViewSegments\.value\) return;/)
})
