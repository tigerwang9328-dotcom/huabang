// 财务设置编辑页 — 按店铺组分组排序（与 dashboard 店铺经营日报同序）
// 输入扁平 store 行 + 店铺组(含 parent_group_id/members)，输出有序 displayRows：
// 顶层(未分组店 + 顶层组块)按销售额降序；组块内 = 成员店(降序) + 子组块(递归) + 本组「合计/编辑」行(块末)。
// 组行由调用方 buildGroupRow 构造（带 getter/setter 访问器，复用现有 v-model 实现组级编辑）。
import { computed, type Ref } from "vue"

export interface GroupInfo {
  id: number
  name: string
  parent_group_id: number | null
  members: { store_id: number }[]
}

export interface GroupMeta {
  group_id: number
  group_name: string
  level: number
  members: any[]   // 子树内在场的 store 行（引用，可直接读写）
}

interface Options {
  saleKey?: string
  buildGroupRow: (meta: GroupMeta) => any
}

export function useGroupedRows(stores: Ref<any[]>, groups: Ref<GroupInfo[]>, opts: Options) {
  const saleKey = opts.saleKey || "sale_amount"
  const hasGroups = computed(() => (groups.value?.length || 0) > 0)

  const displayRows = computed<any[]>(() => {
    const rows = stores.value || []
    if (!hasGroups.value) return rows

    const storeById = new Map<number, any>()
    for (const r of rows) storeById.set(Number(r.store_id), r)

    const childrenOf = new Map<number | null, number[]>()
    const membersOf = new Map<number, number[]>()
    const byId = new Map<number, GroupInfo>()
    const validIds = new Set(groups.value.map(g => g.id))
    for (const g of groups.value) {
      byId.set(g.id, g)
      membersOf.set(g.id, (g.members || []).map(m => Number(m.store_id)))
    }
    for (const g of groups.value) {
      const pid = g.parent_group_id != null && validIds.has(g.parent_group_id) ? g.parent_group_id : null
      if (!childrenOf.has(pid)) childrenOf.set(pid, [])
      childrenOf.get(pid)!.push(g.id)
    }

    const groupedStoreIds = new Set<number>()
    for (const ids of membersOf.values()) ids.forEach(i => groupedStoreIds.add(i))

    const subtreeCache = new Map<number, any[]>()
    function subtreeRows(gid: number): any[] {
      if (subtreeCache.has(gid)) return subtreeCache.get(gid)!
      const out: any[] = []
      for (const sid of (membersOf.get(gid) || [])) {
        const r = storeById.get(sid)
        if (r) out.push(r)
      }
      for (const cid of (childrenOf.get(gid) || [])) out.push(...subtreeRows(cid))
      subtreeCache.set(gid, out)
      return out
    }
    const groupSale = (gid: number) => subtreeRows(gid).reduce((s, r) => s + Number(r[saleKey] || 0), 0)

    function emitGroup(gid: number, depth: number): any[] {
      const g = byId.get(gid)!
      const entries: { kind: string; sale: number; obj: any }[] = []
      for (const sid of (membersOf.get(gid) || [])) {
        const r = storeById.get(sid)
        if (r) entries.push({ kind: "store", sale: Number(r[saleKey] || 0), obj: r })
      }
      for (const cid of (childrenOf.get(gid) || [])) entries.push({ kind: "group", sale: groupSale(cid), obj: cid })
      entries.sort((a, b) => b.sale - a.sale)

      const out: any[] = []
      for (const e of entries) {
        if (e.kind === "store") { e.obj._level = depth + 1; e.obj._group_id = gid; out.push(e.obj) }
        else out.push(...emitGroup(e.obj, depth + 1))
      }
      out.push(opts.buildGroupRow({
        group_id: gid, group_name: g.name, level: depth, members: subtreeRows(gid),
      }))
      return out
    }

    const top: { kind: string; sale: number; obj: any }[] = []
    for (const r of rows) {
      const sid = Number(r.store_id)
      if (!groupedStoreIds.has(sid)) { r._level = 0; r._group_id = null; top.push({ kind: "store", sale: Number(r[saleKey] || 0), obj: r }) }
    }
    for (const gid of (childrenOf.get(null) || [])) top.push({ kind: "group", sale: groupSale(gid), obj: gid })
    top.sort((a, b) => b.sale - a.sale)

    const out: any[] = []
    for (const e of top) {
      if (e.kind === "store") out.push(e.obj)
      else out.push(...emitGroup(e.obj, 0))
    }
    return out
  })

  const rowClassName = ({ row }: { row: any }) => (row?._row_kind === "group" ? "fin-group-row" : "")
  const isGroup = (row: any) => row?._row_kind === "group"

  return { displayRows, hasGroups, rowClassName, isGroup }
}
