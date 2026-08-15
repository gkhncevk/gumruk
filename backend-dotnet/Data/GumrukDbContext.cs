using GumrukApi.Models;
using Microsoft.EntityFrameworkCore;

namespace GumrukApi.Data
{
    public class GumrukDbContext : DbContext
    {
        public GumrukDbContext(DbContextOptions<GumrukDbContext> options) : base(options)
        {
        }

        public DbSet<AnalizKaydi> AnalizKayitlari { get; set; }
        public DbSet<Feedback> Feedbackler { get; set; }
        public DbSet<KuralKutuphanesi> KuralKutuphaneleri { get; set; }
    }
}
