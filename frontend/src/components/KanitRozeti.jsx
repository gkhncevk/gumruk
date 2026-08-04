function KanitRozeti({ kaynakTipi }) {
  const guclu = kaynakTipi === "btb_karari";
  return (
    <span className={`kanit-rozeti ${guclu ? "guclu" : "zayif"}`}>
      {guclu ? "Güçlü kanıt (gerçek BTB kararı)" : "Zayıf kanıt (sadece resmi kod)"}
    </span>
  );
}
export default KanitRozeti;