using Sample.Api.Links;

namespace Sample.Api.Controllers
{
    [ApiController]
    [Route(RouteHelper.Payslip.Controller)]
    public class PayslipController : ControllerBase
    {
        [Authorize(Policy = "PayslipUsersOnly")]
        [HttpGet(RouteHelper.Payslip.AllPayslipsWithoutOdp)]
        [HttpGet(RouteHelper.Payslip.AllPayslips)]
        public async Task<ActionResult<PayslipListDto>> QueryPayslips(long? odpUserId, [FromQuery] PayslipQuery query)
        {
            return Ok();
        }

        [HttpGet(RouteHelper.Payslip.Export)]
        public ActionResult<ExportDto> Export(long odpUserId) => Ok();

        [HttpGet]
        [Route(RouteHelper.Payslip.GetDocumentFile)]
        public IActionResult DocumentFile(string payslipId) => Ok();

        [HttpGet(nameof(Status))]
        public IActionResult Status() => Ok();

        [HttpDelete(RouteHelper.Payslip.Missing)]
        public IActionResult Remove(string payslipId) => NoContent();
    }
}
