namespace GumrukApi.Models
{
    public record AnalizIstek(
        string EsyaTanimi,
        string? BeyanEdilenGtip,
        string OnerilenGtip,
        string RiskSeviyesi,
        double BenzerlikSkoru
    );
}
