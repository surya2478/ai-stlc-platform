import { useEffect, useState } from "react";
import { usersApi, type UserAccount } from "@/lib/api";

// Module-level cache to avoid multiple redundant requests across components
let globalUserMap: Record<number, string> | null = null;
let globalUserMapPromise: Promise<Record<number, string>> | null = null;
let currentUserCache: UserAccount | null = null;
let currentUserPromise: Promise<UserAccount | null> | null = null;

export function useUserDirectory() {
  const [userMap, setUserMap] = useState<Record<number, string>>(globalUserMap || {});
  const [currentUser, setCurrentUser] = useState<UserAccount | null>(currentUserCache);
  const [loading, setLoading] = useState(!globalUserMap || !currentUserCache);

  useEffect(() => {
    let active = true;

    async function loadDirectory() {
      try {
        // Fetch current user if not cached
        let current: UserAccount | null = currentUserCache;
        if (!current) {
          if (!currentUserPromise) {
            currentUserPromise = usersApi.me().then(res => {
              currentUserCache = res.data;
              return res.data;
            }).catch(err => {
              console.error("Failed to fetch current user in directory:", err);
              currentUserPromise = null;
              return null;
            });
          }
          current = await currentUserPromise;
        }

        if (active && current) {
          setCurrentUser(current);
        }

        // Fetch user list
        let map = globalUserMap;
        if (!map) {
          if (!globalUserMapPromise) {
            globalUserMapPromise = (async () => {
              const newMap: Record<number, string> = {};
              // Add current user to map immediately
              if (current) {
                newMap[current.id] = current.full_name;
              }
              try {
                // Try to get all users
                const res = await usersApi.list({ limit: 200 });
                res.data.forEach(u => {
                  newMap[u.id] = u.full_name;
                });
              } catch (err) {
                // If it fails (e.g. non-admin doesn't have permission), we gracefully fallback
                console.warn("Could not load full user directory (expected for non-admins):", err);
              }
              globalUserMap = newMap;
              return newMap;
            })();
          }
          map = await globalUserMapPromise;
        }

        if (active) {
          setUserMap(map);
        }
      } catch (err) {
        console.error("useUserDirectory error:", err);
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadDirectory();

    return () => {
      active = false;
    };
  }, []);

  const resolveUser = (id?: number) => {
    if (id === undefined || id === null || id === 0) return "—";
    return userMap[id] || `User #${id}`;
  };

  return { resolveUser, currentUser, loading, userMap };
}
