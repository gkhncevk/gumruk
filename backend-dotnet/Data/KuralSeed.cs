using CsvHelper;
using GumrukApi.Models;
using Microsoft.EntityFrameworkCore;
using System.Globalization;

namespace GumrukApi.Data
{
    public static class KuralSeed
    {
        public static async Task CalistirAsync(GumrukDbContext db, string icerikKokYolu)
        {
            if (await db.KuralKutuphaneleri.AnyAsync())
            {
                return;
            }

            var csvYolu = Path.Combine(icerikKokYolu, "..", "ai-service", "data", "kurallar_kutuphanesi.csv");

            using var reader = new StreamReader(csvYolu);
            using var csv = new CsvReader(reader, CultureInfo.InvariantCulture);

            var kayitlar = new List<KuralKutuphanesi>();
            csv.Read();
            csv.ReadHeader();
            while (csv.Read())
            {
                kayitlar.Add(new KuralKutuphanesi
                {
                    KuralId = csv.GetField("kural_id") ?? "",
                    IlgiliPozisyonlar = csv.GetField("ilgili_pozisyonlar") ?? "",
                    KuralMetni = csv.GetField("kural_metni") ?? "",
                });
            }

            db.KuralKutuphaneleri.AddRange(kayitlar);
            await db.SaveChangesAsync();
        }
    }
}
