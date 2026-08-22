import { createContext } from "react";
import type { UserOut } from "../api/client";

export interface AuthContextValue {
  user: UserOut | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  verifyEmail: (token: string) => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
