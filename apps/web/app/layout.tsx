export const metadata = {
  title: "AION",
  description: "Music intelligence — organic technical library system",
};

import "./globals.css";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-body antialiased">
        {children}
        <footer className="mx-auto max-w-7xl px-6 py-6 text-center">
          <p className="text-[11px] text-aion-text-faint">
            Music metadata via{" "}
            <a
              href="https://getsongbpm.com"
              className="text-aion-text-muted underline-offset-2 hover:text-aion-text-secondary hover:underline"
            >
              GetSongBPM
            </a>
          </p>
        </footer>
      </body>
    </html>
  );
}
