package chipsldpc

import org.scalatest.freespec.AnyFreeSpec

final class EndToEndSpec extends AnyFreeSpec {
  private val example = DecoderProblem.parse(
    """{"schema":1,"n":7,"row_ones":[[3,4,5,6],[1,2,5,6],[0,2,4,6]],"prior":[1,2,3,4,5,6,7],"syndrome":[1,0,1],"iterations":4}""",
  )

  "the example defines one valid Steane experiment" in {
    assert(example.graph.checkCount == 3)
    assert(example.graph.variableCount == 7)
    assert(example.graph.edgeCount == 12)
    assert(example.control(1) == 1 && example.control(8) == 7)
  }

  "problem dimensions, values, and schema are checked before elaboration" in {
    assertThrows[IllegalArgumentException](example.copy(schema = 2))
    assertThrows[IllegalArgumentException](example.copy(prior = example.prior.drop(1)))
    assertThrows[IllegalArgumentException](example.copy(prior = example.prior.updated(0, 16)))
    assertThrows[IllegalArgumentException](example.copy(syndrome = example.syndrome.drop(1)))
    assertThrows[IllegalArgumentException](example.copy(iterations = 0))
    assertThrows[IllegalArgumentException](DecoderProblem.parse(
      """{"schema":1,"n":2,"row_ones":[[0,1]],"prior":[1,1],"syndrome":[2],"iterations":1}""",
    ))
  }
}
