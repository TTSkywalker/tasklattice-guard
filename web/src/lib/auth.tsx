import { createContext, useCallback, useContext, useEffect, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import i18n, { setApplicationLanguage, type SupportedLanguage } from "@/i18n";
import {
  getAuthStatus,
  login as loginRequest,
  logout as logoutRequest,
  setupAdmin as setupAdminRequest,
  updateMe,
  type AuthStatus,
  type IdentityUser,
} from "@/lib/api";
import { queryKeys } from "@/features/query-keys";

type LoginInput = { email: string; password: string };
type SetupInput = LoginInput & { display_name: string; preferred_language: SupportedLanguage };

type AuthContextValue = {
  status: AuthStatus | undefined;
  user: IdentityUser | null;
  isLoading: boolean;
  error: unknown;
  login: (input: LoginInput) => Promise<void>;
  setup: (input: SetupInput) => Promise<void>;
  logout: () => Promise<void>;
  setLanguage: (language: SupportedLanguage) => Promise<void>;
  loginPending: boolean;
  setupPending: boolean;
  logoutPending: boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const statusQuery = useQuery({
    queryKey: queryKeys.auth,
    queryFn: getAuthStatus,
    staleTime: 30_000,
    retry: false,
  });

  const setAuthenticatedUser = useCallback((user: IdentityUser) => {
    queryClient.setQueryData<AuthStatus>(queryKeys.auth, {
      setup_required: false,
      authenticated: true,
      user,
    });
  }, [queryClient]);

  const loginMutation = useMutation({
    mutationFn: loginRequest,
    onSuccess: ({ user }) => setAuthenticatedUser(user),
  });
  const setupMutation = useMutation({
    mutationFn: setupAdminRequest,
    onSuccess: ({ user }) => setAuthenticatedUser(user),
  });
  const logoutMutation = useMutation({
    mutationFn: logoutRequest,
    onSettled: () => {
      queryClient.clear();
      queryClient.setQueryData<AuthStatus>(queryKeys.auth, {
        setup_required: false,
        authenticated: false,
        user: null,
      });
    },
  });

  const user = statusQuery.data?.user ?? null;

  useEffect(() => {
    if (user?.preferred_language && user.preferred_language !== i18n.language) {
      void setApplicationLanguage(user.preferred_language);
    }
  }, [user?.preferred_language]);

  useEffect(() => {
    const handleUnauthorized = () => void queryClient.invalidateQueries({ queryKey: queryKeys.auth });
    window.addEventListener("tasklattice:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("tasklattice:unauthorized", handleUnauthorized);
  }, [queryClient]);

  const setLanguage = useCallback(async (language: SupportedLanguage) => {
    if (!user) {
      await setApplicationLanguage(language);
      return;
    }
    const result = await updateMe({ preferred_language: language });
    setAuthenticatedUser(result.user);
    await setApplicationLanguage(result.user.preferred_language);
  }, [setAuthenticatedUser, user]);

  return (
    <AuthContext.Provider
      value={{
        status: statusQuery.data,
        user,
        isLoading: statusQuery.isLoading,
        error: statusQuery.error,
        login: async (input) => { await loginMutation.mutateAsync(input); },
        setup: async (input) => { await setupMutation.mutateAsync(input); },
        logout: async () => { await logoutMutation.mutateAsync(); },
        setLanguage,
        loginPending: loginMutation.isPending,
        setupPending: setupMutation.isPending,
        logoutPending: logoutMutation.isPending,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider.");
  return value;
}
