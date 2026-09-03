package chipsldpc.osd

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import chipsldpc.Gf2Reference
import chipsldpc.graph.TannerGraph
import chipsldpc.sort.{MagnitudeAscending, SignedAscending}
import org.scalatest.freespec.AnyFreeSpec

final class FilteredOsd0Spec extends AnyFreeSpec with ChiselSim {
  private val graph = TannerGraph.fromRows(
    7,
    Seq(Seq(3, 4, 5, 6), Seq(1, 2, 5, 6), Seq(0, 2, 4, 6)),
  )
  private val oneStage = FilteredOsd0Config(
    graph, softBits = 5, threshold = 1, prefixes = Seq(5),
  )

  private def run(
      dut: FilteredOsd0,
      config: FilteredOsd0Config,
      soft: Vector[Int],
      syndrome: Int,
      scope: Option[Set[Int]] = None,
      resultStalls: Int = 0,
  ): Unit = {
    val graph = config.graph
    val columns = graph.colOnes.map(_.foldLeft(0)((bits, row) => bits | 1 << row))
    val eligible = soft.indices.filter(i => (config.order match {
      case MagnitudeAscending => soft(i).abs < config.threshold
      case SignedAscending => soft(i) < config.threshold
    }) && scope.forall(_(i))).sortBy(i => (
      if (config.order == MagnitudeAscending) soft(i).abs else soft(i), i,
    )).toVector
    val kept = eligible.take(config.maxSelected)
    val target = (0 until graph.checkCount).filter(i => (syndrome & 1 << i) != 0).toSet
    def solve(selected: Vector[Int], width: Int) = {
      val rows = graph.rowOnes.indices.map(row => selected.indices.foldLeft(0)((bits, slot) =>
        bits | (if ((columns(selected(slot)) & 1 << row) != 0) 1 << slot else 0)
      ))
      val active = rows.indices.count(row => rows(row) != 0 || target(row))
      val solved = Gf2Reference.solve(rows, graph.rowOnes.indices.map(syndrome >> _ & 1), selected.size)
      val cycles = if (active == 0) 0 else active + 3 * width + 1
      (solved, active, cycles)
    }
    val rejected = eligible.size > config.maxSelected && config.rejectOverflow
    var attempt = 0
    var selectedColumns = kept.take(config.prefixes.head)
    var solved = solve(selectedColumns, config.prefixes.head)
    var solverCycles = solved._3
    while (!rejected && !solved._1.consistent && attempt + 1 < config.prefixes.size &&
           kept.size > config.prefixes(attempt)) {
      attempt += 1
      selectedColumns = kept.take(config.prefixes(attempt))
      solved = solve(selectedColumns, config.prefixes(attempt))
      solverCycles += solved._3
    }
    val (golden, activeRows, _) = solved
    val expectedStatus =
      if (rejected) OsdStatus.Overflow
      else if (!golden.consistent) OsdStatus.Inconsistent
      else OsdStatus.Solved

    dut.io.in.bits.syndrome.zipWithIndex.foreach { case (bit, row) => bit.poke(((syndrome >> row) & 1).B) }
    dut.io.in.bits.soft.zip(soft).foreach { case (port, value) => port.poke(value.S) }
    dut.io.in.bits.inScopeValid.poke(scope.nonEmpty.B)
    dut.io.in.bits.inScope.zipWithIndex.foreach { case (bit, i) => bit.poke(scope.forall(_(i)).B) }
    dut.io.in.valid.poke(true.B)
    dut.io.result.ready.poke((resultStalls == 0).B)
    dut.io.in.ready.expect(true.B)
    dut.clock.step()
    dut.io.in.valid.poke(false.B)

    val correction = Vector.newBuilder[(Int, Int, Boolean)]
    var elapsed = 0
    while (!dut.io.result.valid.peek().litToBoolean && elapsed < 100) {
      if (dut.io.correction.valid.peek().litToBoolean) correction += ((
        dut.io.correction.bits.index.peek().litValue.toInt,
        dut.io.correction.bits.value.peek().litValue.toInt,
        dut.io.correction.bits.last.peek().litToBoolean,
      ))
      dut.clock.step()
      elapsed += 1
    }
    dut.io.result.valid.expect(true.B)
    dut.io.result.bits.status.expect(expectedStatus)
    dut.io.result.bits.selected.expect(selectedColumns.size.U)
    dut.io.result.bits.activeRows.expect(activeRows.U)
    dut.io.result.bits.cycles.expect(elapsed.U)

    val observed = correction.result()
    if (expectedStatus == OsdStatus.Solved) {
      assert(observed.map(_._1) == selectedColumns)
      assert(observed.indices.forall(i => observed(i)._3 == (i == observed.size - 1)))
      val correctedSyndrome = observed.foldLeft(0) { case (sum, (index, value, _)) =>
        sum ^ (if (value != 0) columns(index) else 0)
      }
      assert(correctedSyndrome == syndrome)
      assert(observed.map(_._2) == golden.bits)
    } else assert(observed.isEmpty)

    if (rejected) solverCycles = 0
    dut.io.result.bits.solverCycles.expect(solverCycles.U)
    val sorterCycles = graph.variableCount + eligible.size
    val expectedCycles =
      if (rejected) sorterCycles
      else if (activeRows == 0) sorterCycles + 3
      else sorterCycles + solverCycles +
        4 * attempt + (if (expectedStatus == OsdStatus.Solved) selectedColumns.size + 2 else 3)
    assert(elapsed == expectedCycles)
    for (_ <- 0 until resultStalls) {
      dut.clock.step()
      dut.io.result.valid.expect(true.B)
      dut.io.result.bits.cycles.expect(elapsed.U)
    }
    dut.io.result.ready.poke(true.B)
    dut.clock.step()
  }

  "filters, scopes, solves, and reports exact cycle counts" in {
    simulate(new FilteredOsd0(oneStage)) { dut =>
      dut.io.in.valid.poke(false.B)
      dut.io.correction.ready.poke(true.B)
      dut.io.result.ready.poke(true.B)

      run(dut, oneStage, Vector(0, -3, 2, -5, 1, 4, 3), syndrome = 5)
      run(dut, oneStage, Vector(-4, -3, -2, 2, 3, 4, 5), syndrome = 6)
      run(dut, oneStage, Vector(-4, 3, 2, 1, 5, 4, 6), syndrome = 1)
      run(dut, oneStage, Vector(2, 3, 2, 1, 5, 4, -4), syndrome = 1)
      run(dut, oneStage, Vector.fill(7)(2), syndrome = 0)
      run(dut, oneStage, Vector(-7, -6, -5, -4, -3, -2, 2), syndrome = 0)
      run(
        dut, oneStage,
        Vector(-6, -5, -4, -3, -2, 0, 2),
        syndrome = 7,
        scope = Some(Set(0, 1, 3)),
        resultStalls = 3,
      )
    }
  }

  "sorts once and advances only after an inconsistent prefix" in {
    val progressive = FilteredOsd0Config(
      graph, softBits = 5, threshold = 17, prefixes = Seq(2, 3, 4),
      rejectOverflow = false, order = MagnitudeAscending,
    )
    simulate(new FilteredOsd0(progressive)) { dut =>
      dut.io.in.valid.poke(false.B)
      dut.io.correction.ready.poke(true.B)
      dut.io.result.ready.poke(true.B)
      run(dut, progressive, Vector(2, 1, 3, 0, 6, 5, 4), syndrome = 3)
      run(dut, progressive, Vector(0, 1, 4, 2, 6, 5, 3), syndrome = 1)
      run(dut, progressive, Vector(0, 1, 2, 3, 6, 5, 4), syndrome = 1)
    }
    val duplicateRows = TannerGraph.fromRows(4, Seq(Seq(0, 1, 2, 3), Seq(0, 1, 2, 3)))
    val inconsistent = FilteredOsd0Config(
      duplicateRows, softBits = 5, threshold = 17, prefixes = Seq(2, 3, 4),
      rejectOverflow = false, order = MagnitudeAscending,
    )
    simulate(new FilteredOsd0(inconsistent)) { dut =>
      dut.io.in.valid.poke(false.B)
      dut.io.correction.ready.poke(true.B)
      dut.io.result.ready.poke(true.B)
      run(dut, inconsistent, Vector(0, 1, 2, 3), syndrome = 1)
    }
  }
}
