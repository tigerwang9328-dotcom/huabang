import { storeToRefs } from "pinia";

import type { MumarenFinanceBook } from "@/api/mumarenFinanceCenter";
import { useMumarenFinanceBookStore } from "@/stores/mumarenFinanceBook";

export const useMumarenFinanceBook = () => {
  const store = useMumarenFinanceBookStore();
  const { bookId, isReadonly } = storeToRefs(store);

  const initializeBook = (books: MumarenFinanceBook[]) => {
    if (!books.some((book) => book.id === bookId.value)) {
      bookId.value = books[0]?.id;
    }
  };

  const selectBook = (nextBookId: number) => {
    bookId.value = nextBookId;
  };

  return { bookId, isReadonly, initializeBook, selectBook };
};
