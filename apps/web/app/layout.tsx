export const metadata = {
  title: "AION — Your Crate",
  description: "Provider-independent music library explorer.",
};

import "./globals.css";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans antialiased">
        {children}
        <footer className="mx-auto max-w-6xl px-6 py-6 text-center text-xs text-zinc-500">
          Music metadata provided by{" "}
          <a href="https://getsongbpm.com" className="underline underline-offset-2 hover:text-zinc-300">
            GetSongBPM
          </a>
        </footer>
      </body>
    </html>
  );
}
