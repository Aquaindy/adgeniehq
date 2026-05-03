import { create } from "zustand";
import { persist } from "zustand/middleware";

type WorkspaceState = {
  currentWorkspaceId: string | null;
  setCurrentWorkspaceId: (id: string | null) => void;
};

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      currentWorkspaceId: null,
      setCurrentWorkspaceId: (id) => set({ currentWorkspaceId: id }),
    }),
    {
      name: "advanta.workspace",
    },
  ),
);
