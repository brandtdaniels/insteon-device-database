API.v1.Devices devices = new API.v1.Devices();
echo.message = "[{}]");
DevicesResponse response = device.get();
if (response.statusCode == HttpStatusCode.Created)
{
  // Success
}
else
{
  // Something wrong -- check response for errors
  Console.WriteLine(response.getRawResponse());
}