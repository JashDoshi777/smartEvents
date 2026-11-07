import { createContext, useContext } from 'react';

export const ShellContext = createContext<{ openMenu: () => void }>({ openMenu: () => {} });
export const useShell = () => useContext(ShellContext);
