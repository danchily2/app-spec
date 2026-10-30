using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Employee.Api.Controllers
{
    [ApiController]
    [Route("employee/api/v1")]
    public class PayslipController : ControllerBase
    {
        // GET employee/api/v1/employees/{odpUserId}/payslips
        [HttpGet("employees/{odpUserId}/payslips")]
        [Authorize(Policy = "PayslipUsersReadPolicy")]
        public async Task<ActionResult<PayslipListDto>> GetPayslips(string odpUserId, [FromQuery] PayslipQuery query)
        {
            return Ok();
        }

        [HttpPost("~/employee/api/v1/payslips/{payslipId}/acknowledge")]
        [Authorize]
        public ActionResult<AckDto> Acknowledge(string payslipId, AckRequest request)
        {
            return Ok();
        }
    }

    [Route("api/v1/[controller]")]
    public class PingController : ControllerBase
    {
        [HttpGet]
        public ActionResult<string> Get() => Ok();

        [HttpDelete("{id}")]
        public IActionResult Remove(int id) => NoContent();
    }
}
