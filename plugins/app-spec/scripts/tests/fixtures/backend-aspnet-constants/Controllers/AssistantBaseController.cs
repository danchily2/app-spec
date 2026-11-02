namespace Sample.Api.Controllers
{
    [Authorize]
    [Route(RouteHelper.V2.ControllerWithVersion)]
    [ApiVersion(RouteHelper.ApiVersion2)]
    public abstract class V2BaseController : ControllerBase
    {
    }

    public class AssistantController : V2BaseController
    {
        [HttpPost("feedback")]
        public ActionResult<FeedbackDto> Feedback(FeedbackRequest request) => Ok();
    }
}
