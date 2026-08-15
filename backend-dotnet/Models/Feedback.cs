namespace GumrukApi.Models
{
    public class Feedback
    {
        public int Id { get; set; }
        public int AnalizKaydiId { get; set; }
        public AnalizKaydi? AnalizKaydi { get; set; }
        public bool DogruMu { get; set; }
        public string? Notlar { get; set; }
        public DateTime OlusturulmaTarihi { get; set; } = DateTime.UtcNow;
    }
}