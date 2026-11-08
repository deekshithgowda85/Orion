"use client";

import { useEffect, useRef } from "react";
import { useAuth } from "@clerk/nextjs";
import { useQueryClient } from "@tanstack/react-query";
import { setAuthTokenGetter } from "@/lib/api";
import { MOCK_MODE } from "@/lib/mock-mode";
import { useResearchStore } from "@/store/research";

function ClerkAuthBridge() {
  const { getToken, orgId, isLoaded } = useAuth();
  const queryClient = useQueryClient();
  const getTokenRef = useRef(getToken);
  getTokenRef.current = getToken;
  const lastOrg = useRef<string | null | undefined>(undefined);

  // fetch() calls carry the session JWT (includes the active org). EventSource
  // cannot set headers, so the SSE stream relies on the Clerk session cookie instead.
  useEffect(() => {
    setAuthTokenGetter(() => getTokenRef.current());
    return () => setAuthTokenGetter(null);
  }, []);

  // Tenant isolation in the browser: when the active organization changes, drop every
  // cached query and every live stream so nothing from the previous org is shown.
  useEffect(() => {
    if (!isLoaded) return;
    const current = orgId ?? null;
    if (lastOrg.current !== undefined && lastOrg.current !== current) {
      useResearchStore.getState().reset();
      queryClient.clear();
    }
    lastOrg.current = current;
  }, [orgId, isLoaded, queryClient]);

  return null;
}

export function AuthBridge() {
  return MOCK_MODE ? null : <ClerkAuthBridge />;
}
