import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { mumarenFinanceCenterApi, type MumarenFinanceBook } from "@/api/mumarenFinanceCenter";

export const useMumarenFinanceBookStore = defineStore("mumarenFinanceBook", () => {
  const books = ref<MumarenFinanceBook[]>([]);
  const bookId = ref<number>();
  const loading = ref(false);
  const error = ref("");
  const selectedBook = computed(() => books.value.find((book) => book.id === bookId.value));
  const isReadonly = computed(() => Boolean(selectedBook.value?.is_readonly));

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
