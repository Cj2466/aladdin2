import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  fetchCurrentUser,
  loginUser,
  logoutUser,
  registerUser,
  setUnauthorizedHandler,
  verifyEmailToken,
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

  async function register(email: string, password: string, acceptedTerms: boolean) {
    // Registering no longer starts a session — the account must be
    // verified by email first. registerUser's response only confirms the
    // account was created and a verification email is on its way.
    await registerUser(email, password, acceptedTerms);
  }

  async function logout() {
    await logoutUser();
    setUser(null);
  }

  async function verifyEmail(token: string) {
    // Unlike register, verifying does log the user in — it's itself
    // strong proof of email ownership via a flow already in progress.
    const verifiedUser = await verifyEmailToken(token);
    setUser(verifiedUser);
  }

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout, verifyEmail }}>
      {children}
    </AuthContext.Provider>
  );
}
