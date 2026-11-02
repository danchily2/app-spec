namespace Sample.Api.Links
{
    internal static class RouteHelper
    {
        public const string ApiVersion2 = "2.0";
        public const string Version = "v1";
        private const string RootOdpUser = "api/" + Version + "/employees/{odpUserId}";
        private const string RouteWithVersion = "api/v{version:apiVersion}";

        public static class V2
        {
            public const string ControllerWithVersion = RouteWithVersion + "/[controller]";
        }

        internal static class Payslip
        {
            public const string Controller = "";
            public const string AllPayslips = RootOdpUser + "/allpayslips";
            public const string AllPayslipsWithoutOdp = "api/v1/payslip/allpayslips";
            public static readonly string Export = $"{RootOdpUser}/payslips/export";
            public const string GetDocumentFile = "api/v1/payslip/getpayslipdocumentfile";
        }
    }
}
