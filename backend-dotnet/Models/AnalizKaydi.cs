namespace GumrukApi.Models;

public class AnalizKaydi
{
    public int Id { get; set; }
    public string EsyaTanimi { get; set; } = string.Empty;
    public string? BeyanEdilenGtip { get; set; }
    public string OnerilenGtip { get; set; } = string.Empty;
    public string RiskSeviyesi { get; set; } = string.Empty;
    public double BenzerlikSkoru { get; set; }
    public DateTime OlusturulmaTarihi { get; set; } = DateTime.UtcNow;
}