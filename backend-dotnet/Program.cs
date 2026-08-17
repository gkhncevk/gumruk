using GumrukApi.Data;
using GumrukApi.Models;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);

// Add services to the container.
// Learn more about configuring OpenAPI at https://aka.ms/aspnet/openapi
builder.Services.AddOpenApi();

builder.Services.AddDbContext<GumrukDbContext>(options =>
    options.UseNpgsql(builder.Configuration.GetConnectionString("GumrukDb")));

var app = builder.Build();

// Configure the HTTP request pipeline.
if (app.Environment.IsDevelopment())
{
    app.MapOpenApi();
}
using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<GumrukDbContext>();
    await KuralSeed.CalistirAsync(db, app.Environment.ContentRootPath);
}
app.UseHttpsRedirection();

app.MapGet("/api/kurallar", async (GumrukDbContext db) =>
{
    var kurallar = await db.KuralKutuphaneleri.ToListAsync();
    return kurallar;
});

app.MapPost("/api/analiz", async (AnalizIstek istek, GumrukDbContext db) =>
{
    var kayit = new AnalizKaydi
    {
        EsyaTanimi = istek.EsyaTanimi,
        BeyanEdilenGtip = istek.BeyanEdilenGtip,
        OnerilenGtip = istek.OnerilenGtip,
        RiskSeviyesi = istek.RiskSeviyesi,
        BenzerlikSkoru = istek.BenzerlikSkoru,
    };
    db.AnalizKayitlari.Add(kayit);
    await db.SaveChangesAsync();
    return Results.Created($"/api/analiz/{kayit.Id}", kayit);
});

var summaries = new[]
{
    "Freezing", "Bracing", "Chilly", "Cool", "Mild", "Warm", "Balmy", "Hot", "Sweltering", "Scorching"
};

app.MapGet("/weatherforecast", () =>
{
    var forecast =  Enumerable.Range(1, 5).Select(index =>
        new WeatherForecast
        (
            DateOnly.FromDateTime(DateTime.Now.AddDays(index)),
            Random.Shared.Next(-20, 55),
            summaries[Random.Shared.Next(summaries.Length)]
        ))
        .ToArray();
    return forecast;
})
.WithName("GetWeatherForecast");

app.Run();

record WeatherForecast(DateOnly Date, int TemperatureC, string? Summary)
{
    public int TemperatureF => 32 + (int)(TemperatureC / 0.5556);
}
