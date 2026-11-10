// EXPORT_CONTRACT hero-mode check, Unity side (eval_file script, not compiled into the project):
// dumps every hero FBX mesh as Unity imported it (positions / normals / tangents / UV0) to Temp/claude/hero_dump/.
// Run: unity command eval_file --file Tools/Unity/hero_import_dump.cs ; then Tools/Blender/heroes/hero_import_compare.py
var outDir = "Temp/claude/hero_dump";
System.IO.Directory.CreateDirectory(outDir);
var sb = new System.Text.StringBuilder();
var ci = System.Globalization.CultureInfo.InvariantCulture;
foreach (var hero in new[] { "Gate", "Terminal", "LeverStand", "ServiceArm" })
{
    foreach (var guid in UnityEditor.AssetDatabase.FindAssets("t:Model", new[] { "Assets/Environment/Heroes/" + hero }))
    {
        var path = UnityEditor.AssetDatabase.GUIDToAssetPath(guid);
        var root = UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.GameObject>(path);
        var mfs = root.GetComponentsInChildren<UnityEngine.MeshFilter>(true);
        var name = System.IO.Path.GetFileNameWithoutExtension(path);
        var t = root.transform;
        sb.AppendLine($"{name}: root pos {t.localPosition.ToString("F5")} rot {t.localEulerAngles.ToString("F3")} scale {t.localScale.ToString("F4")} meshFilters {mfs.Length}");
        var f = new System.Text.StringBuilder();
        foreach (var mf in mfs)
        {
            var m = mf.sharedMesh; var M = root.transform.worldToLocalMatrix * mf.transform.localToWorldMatrix;
            sb.AppendLine($"  node {mf.name} lpos {mf.transform.localPosition.ToString("F5")} lrot {mf.transform.localEulerAngles.ToString("F3")} lscale {mf.transform.localScale.ToString("F4")} v {m.vertexCount} tris {m.triangles.Length / 3} submeshes {m.subMeshCount} tangents {m.tangents.Length} uv2 {m.uv2.Length} bounds {m.bounds.min.ToString("F4")}..{m.bounds.max.ToString("F4")}");
            var v = m.vertices; var n = m.normals; var tg = m.tangents; var uv = m.uv;
            for (int i = 0; i < v.Length; i++)
            {
                var p = M.MultiplyPoint3x4(v[i]); var q = M.MultiplyVector(n[i]).normalized;
                var tt = tg.Length > 0 ? (UnityEngine.Vector3)M.MultiplyVector(tg[i]).normalized : UnityEngine.Vector3.zero;
                var w = tg.Length > 0 ? tg[i].w : 0f;
                f.AppendLine(string.Format(ci, "{0:R} {1:R} {2:R} {3:R} {4:R} {5:R} {6:R} {7:R} {8:R} {9} {10:R} {11:R}", p.x, p.y, p.z, q.x, q.y, q.z, tt.x, tt.y, tt.z, w, uv[i].x, uv[i].y));
            }
        }
        System.IO.File.WriteAllText(outDir + "/" + name + ".txt", f.ToString());
    }
}
return sb.ToString();
