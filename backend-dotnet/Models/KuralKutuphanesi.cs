namespace GumrukApi.Models
{
    public class KuralKutuphanesi
    {
        public int Id { get; set; }
        public string KuralId { get; set; } = string.Empty;
        public string IlgiliPozisyonlar { get; set; } = string.Empty;
        public string KuralMetni { get; set; } = string.Empty;
    }
}