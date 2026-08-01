import { computed, ref, watch } from "vue";
import { defineStore } from "pinia";
import { mumarenFinanceCenterApi, type MumarenFinanceBook } from "@/api/mumarenFinanceCenter";

export const useMumarenFinanceBookStore = defineStore("mumarenFinanceBook", () => {
  const storageKey = "mumaren-finance-center:selected-book-id";
  const stored = Number(window.localStorage.getItem(storageKey));
  const books = ref<MumarenFinanceBook[]>([]);
  const bookId = ref<number | undefined>(Number.isInteger(stored) && stored > 0 ? stored : undefined);
  const loading = ref(false);
  const error = ref("");
  const selectedBook = computed(() => books.value.find((book) => book.id === bookId.value));
  const isReadonly = computed(() => Boolean(selectedBook.value?.is_readonly));

  watch(bookId, (value) => {
    if (value) window.localStorage.setItem(storageKey, String(value));
    else window.localStorage.removeItem(storageKey);
  });

  const loadBooks = async () => {
    loading.value = true;
    error.value = "";
    try {
      books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
      if (bookId.value && !selectedBook.value) bookId.value = undefined;
      if (!bookId.value) bookId.value = books.value[0]?.id;
    } catch {
      error.value = "无法加载独立账簿。";
    } finally {
      loading.value = false;
    }
  };

  return { books, bookId, loading, error, selectedBook, isReadonly, loadBooks };
});
