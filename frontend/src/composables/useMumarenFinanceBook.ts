import { ref, watch } from "vue";

import type { MumarenFinanceBook } from "@/api/mumarenFinanceCenter";

const STORAGE_KEY = "mumaren-finance-center:selected-book-id";

const readStoredBookId = (): number | undefined => {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  const value = Number(raw);
  return Number.isInteger(value) && value > 0 ? value : undefined;
};

const selectedBookId = ref<number | undefined>(readStoredBookId());

watch(selectedBookId, (bookId) => {
  if (bookId) window.localStorage.setItem(STORAGE_KEY, String(bookId));
  else window.localStorage.removeItem(STORAGE_KEY);
});

export const useMumarenFinanceBook = () => {
  const initializeBook = (books: MumarenFinanceBook[]) => {
    if (!books.some((book) => book.id === selectedBookId.value)) {
      selectedBookId.value = books[0]?.id;
    }
  };

  return { bookId: selectedBookId, initializeBook };
};
