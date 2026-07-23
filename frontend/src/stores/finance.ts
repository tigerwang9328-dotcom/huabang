/**
 * 财务中心全局状态 - 当前账套 / 当前期间
 * 所有财务子页面通过此 Store 共享 book_id 和 period
 */
import { defineStore } from "pinia"
import { ref, computed } from "vue"
import request from "@/api/request"

export interface FinBook {
  id: number
  book_code: string
  book_name: string
  company_name: string
  accounting_standard: string
  base_currency: string
  current_period: string
  status: string
  safety_cash_line: number
  enable_ai_summary: boolean
}

export const useFinanceStore = defineStore("finance", () => {
  const bookId = ref<number>(1)
  const currentPeriod = ref<string>("")
  const books = ref<FinBook[]>([])
  const loaded = ref(false)

  const currentBook = computed(() => books.value.find(b => b.id === bookId.value))

  async function loadBooks() {
    try {
      const d: any = await request.get("/finance/books")
      books.value = d.books || []
      // 初始化 bookId
      if (!loaded.value) {
        const saved = localStorage.getItem("fin_book_id")
        bookId.value = saved ? parseInt(saved) : (d.current_book_id || 1)
        loaded.value = true
      }
      // 同步当前期间
      const book = books.value.find(b => b.id === bookId.value)
      if (book?.current_period) {
        currentPeriod.value = book.current_period
      } else {
        const now = new Date()
        currentPeriod.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`
      }
    } catch {}
  }

  function switchBook(id: number) {
    bookId.value = id
    localStorage.setItem("fin_book_id", String(id))
    const book = books.value.find(b => b.id === id)
    if (book?.current_period) {
      currentPeriod.value = book.current_period
    }
  }

  function setPeriod(p: string) {
    currentPeriod.value = p
  }

  return { bookId, currentPeriod, books, loaded, currentBook, loadBooks, switchBook, setPeriod }
}, { persist: false })
