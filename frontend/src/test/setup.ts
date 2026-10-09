import '@testing-library/jest-dom';

const storage: Record<string, string> = {};
const localStorageMock = {
  getItem: (key: string) => storage[key] ?? null,
  setItem: (key: string, value: string) => {
    storage[key] = String(value);
  },
  removeItem: (key: string) => {
    delete storage[key];
  },
  clear: () => {
    Object.keys(storage).forEach((k) => delete storage[k]);
  },
};

const sessionStorageState: Record<string, string> = {};
const sessionStorageMock = {
  getItem: (key: string) => sessionStorageState[key] ?? null,
  setItem: (key: string, value: string) => {
    sessionStorageState[key] = String(value);
  },
  removeItem: (key: string) => {
    delete sessionStorageState[key];
  },
  clear: () => {
    Object.keys(sessionStorageState).forEach((k) => delete sessionStorageState[k]);
  },
};

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
  writable: true,
});
Object.defineProperty(globalThis, 'localStorage', {
  value: localStorageMock,
  writable: true,
});

Object.defineProperty(window, 'sessionStorage', {
  value: sessionStorageMock,
  writable: true,
});
Object.defineProperty(globalThis, 'sessionStorage', {
  value: sessionStorageMock,
  writable: true,
});

