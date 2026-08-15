using System;
using Microsoft.EntityFrameworkCore.Migrations;
using Npgsql.EntityFrameworkCore.PostgreSQL.Metadata;

#nullable disable

namespace GumrukApi.Migrations
{
    /// <inheritdoc />
    public partial class InitialCreate : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "AnalizKayitlari",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    EsyaTanimi = table.Column<string>(type: "text", nullable: false),
                    BeyanEdilenGtip = table.Column<string>(type: "text", nullable: true),
                    OnerilenGtip = table.Column<string>(type: "text", nullable: false),
                    RiskSeviyesi = table.Column<string>(type: "text", nullable: false),
                    BenzerlikSkoru = table.Column<double>(type: "double precision", nullable: false),
                    OlusturulmaTarihi = table.Column<DateTime>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_AnalizKayitlari", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "KuralKutuphaneleri",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    KuralId = table.Column<string>(type: "text", nullable: false),
                    IlgiliPozisyonlar = table.Column<string>(type: "text", nullable: false),
                    KuralMetni = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_KuralKutuphaneleri", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "Feedbackler",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    AnalizKaydiId = table.Column<int>(type: "integer", nullable: false),
                    DogruMu = table.Column<bool>(type: "boolean", nullable: false),
                    Notlar = table.Column<string>(type: "text", nullable: true),
                    OlusturulmaTarihi = table.Column<DateTime>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Feedbackler", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Feedbackler_AnalizKayitlari_AnalizKaydiId",
                        column: x => x.AnalizKaydiId,
                        principalTable: "AnalizKayitlari",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_Feedbackler_AnalizKaydiId",
                table: "Feedbackler",
                column: "AnalizKaydiId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "Feedbackler");

            migrationBuilder.DropTable(
                name: "KuralKutuphaneleri");

            migrationBuilder.DropTable(
                name: "AnalizKayitlari");
        }
    }
}
