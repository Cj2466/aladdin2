import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  fetchCurrentUser,
  loginUser,
  logoutUser,
  registerUser,
  setUnauthorizedHandler,
} from "../api/client";
import type { UserOut } from "../api/client";
import { AuthContext } from "./auth-context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    fetchCurrentUser()
      .then(setUser)
      .finally(() => setIsLoading(false));
    return () => setUnauthorizedHandler(null);
  }, []);

  async function login(email: string, password: string) {
    const loggedInUser = await loginUser(email, password);
    setUser(loggedInUser);
  }

  async function register(email: string, password: string) {
    const newUser = await registerUser(email, password);
    setUser(newUser);
  }

  async function logout() {
    await logoutUser();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
