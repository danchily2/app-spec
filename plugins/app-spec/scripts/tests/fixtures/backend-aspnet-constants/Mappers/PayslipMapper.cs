namespace Sample.Api.Mappers
{
    public class PayslipMapper
    {
        public PayslipDto Map(Payslip source) => new PayslipDto
        {
            Id = source.Id,
            Export = new RestLink(_uriBuilder.CompleteUriForResource(RouteHelper.Payslip.Export,
                new KeyValuePair<string, object>("odpUserId", source.OdpUserId))),
        };
    }
}
