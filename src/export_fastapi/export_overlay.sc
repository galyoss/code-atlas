// Export the Python CPG facts the FastAPI exporter classifies.
// Call .code is the source text pysrc2cpg attached. Predicate decisions use that
// text. This script does not invent comparisons that are absent from the CPG.

@main def exec(out: String) = {
  import io.shiftleft.semanticcpg.language._
  import java.nio.file.{Files, Paths}

  val skip = Set(
    "<operator>.fieldAccess",
    "<operator>.indexAccess",
    "<operator>.alloc"
  )

  def esc(s: String): String = {
    val raw = if (s == null) "" else s
    val b = new StringBuilder
    raw.foreach {
      case '"'  => b.append("\\\"")
      case '\\' => b.append("\\\\")
      case '\n' => b.append("\\n")
      case '\r' => b.append("\\r")
      case '\t' => b.append("\\t")
      case c if c < ' ' => b.append(f"\\u${c.toInt}%04x")
      case c => b.append(c)
    }
    b.toString
  }
  def q(s: String): String = "\"" + esc(s) + "\""
  def clip(s: String, n: Int): String = {
    val raw = if (s == null) "" else s
    if (raw.length <= n) raw else raw.substring(0, n)
  }

  val sb = new StringBuilder
  sb.append("{\"methods\":[")
  var first = true
  cpg.method.filterNot(_.isExternal).foreach { m =>
    if (!first) sb.append(",")
    first = false
    sb.append("{")
    sb.append("\"fullName\":" + q(m.fullName) + ",")
    sb.append("\"name\":" + q(m.name) + ",")
    sb.append("\"file\":" + q(m.filename) + ",")
    sb.append("\"line\":" + m.lineNumber.getOrElse(-1) + ",")
    sb.append("\"endLine\":" + m.lineNumberEnd.getOrElse(-1))
    sb.append("}")
  }
  sb.append("],\"calls\":[")
  first = true
  cpg.call.foreach { c =>
    val name = if (c.name == null) "" else c.name
    if (!skip.contains(name)) {
      if (!first) sb.append(",")
      first = false
      val fileName = c.file.name.headOption.getOrElse("")
      sb.append("{")
      sb.append("\"name\":" + q(name) + ",")
      sb.append("\"methodFullName\":" + q(c.methodFullName) + ",")
      sb.append("\"code\":" + q(clip(c.code, 4000)) + ",")
      sb.append("\"file\":" + q(fileName) + ",")
      sb.append("\"line\":" + c.lineNumber.getOrElse(-1) + ",")
      sb.append("\"caller\":" + q(c.method.fullName) + ",")
      sb.append("\"dispatch\":" + q(c.dispatchType))
      sb.append("}")
    }
  }
  sb.append("]}")
  Files.writeString(Paths.get(out), sb.toString)
  println("wrote " + out + " methods=" + cpg.method.filterNot(_.isExternal).size)
}
