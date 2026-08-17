"use client";

import { useEffect, useState } from "react";

type Kural = {
  id: number;
  kuralId: string;
  ilgiliPozisyonlar: string;
  kuralMetni: string;
};

export default function Home() {
  const [kurallar, setKurallar] = useState<Kural[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState<string | null>(null);

  useEffect(() => {
    fetch("http://localhost:5249/api/kurallar")
      .then((res) => res.json())
      .then((veri) => setKurallar(veri))
      .catch((err) => setHata(err.message))
      .finally(() => setYukleniyor(false));
  }, []);

  if (yukleniyor) return <main className="p-8">Yükleniyor...</main>;
  if (hata) return <main className="p-8 text-red-600">Hata: {hata}</main>;

  return (
    <main className="p-8">
      <h1 className="text-2xl font-bold mb-4">Kural Kütüphanesi</h1>
      <ul className="space-y-3">
        {kurallar.map((kural) => (
          <li key={kural.id} className="border p-3 rounded">
            <strong>{kural.kuralId}</strong> ({kural.ilgiliPozisyonlar}): {kural.kuralMetni}
          </li>
        ))}
      </ul>
    </main>
  );
}
