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

  return { bookId, isReadonly, initializeBook };
};
