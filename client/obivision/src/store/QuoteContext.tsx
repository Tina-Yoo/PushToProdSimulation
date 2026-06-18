import React, { createContext, useContext, useReducer, ReactNode } from "react";
import type { FinalSummarizedResultResponse } from "@/types/api";

export interface UploadedPhoto {
  id: string;
  file?: File;
  preview: string;
  category: string;
  damageOverlay?: string;
}

export interface QuoteState {
  vehicleName: string;
  requestDate: string;
  photos: UploadedPhoto[];
  customerComment: string;
  finalResult: FinalSummarizedResultResponse | null;
}

export type QuoteAction =
  | { type: "SET_VEHICLE_NAME"; vehicleName: string }
  | { type: "ADD_PHOTOS"; photos: UploadedPhoto[] }
  | { type: "REMOVE_PHOTO"; id: string }
  | { type: "UPDATE_PHOTO_CATEGORY"; id: string; category: string }
  | { type: "SET_CUSTOMER_COMMENT"; comment: string }
  | { type: "UPDATE_PHOTO_OVERLAY"; id: string; overlay: string }
  | { type: "CLEAR_PHOTOS" }
  | { type: "SET_QUOTE"; result: FinalSummarizedResultResponse }
  | { type: "RESET" };

const initialState: QuoteState = {
  vehicleName: "",
  requestDate: new Date().toISOString().split("T")[0].replace(/-/g, "."),
  photos: [],
  customerComment: "",
  finalResult: null,
};

function quoteReducer(state: QuoteState, action: QuoteAction): QuoteState {
  switch (action.type) {
    case "SET_VEHICLE_NAME":
      return { ...state, vehicleName: action.vehicleName };

    case "ADD_PHOTOS":
      return { ...state, photos: [...state.photos, ...action.photos] };

    case "REMOVE_PHOTO":
      return {
        ...state,
        photos: state.photos.filter((p) => p.id !== action.id),
      };

    case "UPDATE_PHOTO_CATEGORY":
      return {
        ...state,
        photos: state.photos.map((p) =>
          p.id === action.id ? { ...p, category: action.category } : p
        ),
      };

    case "SET_CUSTOMER_COMMENT":
      return { ...state, customerComment: action.comment };

    case "UPDATE_PHOTO_OVERLAY":
      return {
        ...state,
        photos: state.photos.map((p) =>
          p.id === action.id ? { ...p, damageOverlay: action.overlay } : p
        ),
      };

    case "CLEAR_PHOTOS":
      return { ...state, photos: [] };

    case "SET_QUOTE":
      return { ...state, finalResult: action.result };

    case "RESET":
      return initialState;

    default:
      return state;
  }
}

const QuoteContext = createContext<
  | {
      state: QuoteState;
      dispatch: React.Dispatch<QuoteAction>;
    }
  | undefined
>(undefined);

export function QuoteProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(quoteReducer, initialState);

  return (
    <QuoteContext.Provider value={{ state, dispatch }}>
      {children}
    </QuoteContext.Provider>
  );
}

export function useQuoteContext() {
  const context = useContext(QuoteContext);
  if (!context) {
    throw new Error("useQuoteContext must be used within QuoteProvider");
  }
  return context;
}
