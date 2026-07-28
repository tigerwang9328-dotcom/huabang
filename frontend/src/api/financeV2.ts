import request from "./request";

export interface FinanceV2Book {
  id: number;
  book_code: string;
  book_name: string;
  status: string;
  formal_report_blocked: boolean;
}

export const financeV2Api = {
  listBooks: () => request.get<FinanceV2Book[]>("/finance-center/v2/books"),
};
