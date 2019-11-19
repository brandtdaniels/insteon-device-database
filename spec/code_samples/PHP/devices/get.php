$form = new \API\Entities\Devices();
$form->setMessage("[{}]");
try {
    $pet = $client->devices()->post($form);
} catch (UnprocessableEntityException $e) {
    var_dump($e->getErrors());
}
